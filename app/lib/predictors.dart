import 'package:flutter/material.dart';
import 'beat_model.dart';
import 'predict.dart';
import 'theme.dart';
import 'trust.dart';
import 'widgets.dart';

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

// ----------------------------------------------------------------- Clubs
class ClubsTab extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const ClubsTab(this.data, {required this.onRefresh, super.key});
  @override
  State<ClubsTab> createState() => _ClubsTabState();
}

class _ClubsTabState extends State<ClubsTab> {
  late Map leagues = widget.data['leagues'] as Map;
  late Map<String, String> nameToCode = {
    for (final e in leagues.entries) e.value['name'] as String: e.key as String
  };
  late List<String> orderedNames = _orderedNames();
  late String leagueName = orderedNames.first;
  String? home, away;
  int outHome = 0, outAway = 0;

  List<String> _orderedNames() {
    final names = nameToCode.keys.toList();
    int rank(String n) {
      final i = _leagueOrder.indexOf(nameToCode[n] ?? '');
      return i < 0 ? 99 : i;
    }

    names.sort((a, b) => rank(a).compareTo(rank(b)));
    return names;
  }

  String _disp(String name) =>
      '${_leagueFlag[nameToCode[name]] ?? '⚽'}  $name';

  Map get league => leagues[nameToCode[leagueName]];
  List get teamMaps => league['teams'] as List;
  List<String> get teams => _names(teamMaps);
  Map _team(String n) =>
      teamMaps.firstWhere((t) => t['name'] == n, orElse: () => {});

  @override
  void initState() {
    super.initState();
    final t = teams;
    home = t.first;
    away = t.length > 1 ? t[1] : t.first;
  }

  void _setLeague(String? n) {
    if (n == null) return;
    setState(() {
      leagueName = n;
      final t = teams;
      home = t.first;
      away = t.length > 1 ? t[1] : t.first;
    });
  }

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final r = Predict.club(league, home!, away!,
        outHome: outHome, outAway: outAway);
    final fav = [r.home, r.draw, r.away].reduce((a, b) => a > b ? a : b);
    final rm = r.result;
    final counts = clubCounts(_team(home!), _team(away!));
    final log = (league['log'] as List?) ?? const [];

    return RefreshIndicator(
        onRefresh: widget.onRefresh,
        child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
      _card(context, [
        Picker(
          'League',
          _disp(leagueName),
          [for (final n in orderedNames) _disp(n)],
          (v) {
            if (v == null) return;
            final name = orderedNames.firstWhere((n) => _disp(n) == v,
                orElse: () => leagueName);
            _setLeague(name);
          },
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: Picker('Home', home, teams, (v) => setState(() => home = v))),
          IconButton(
              tooltip: 'Swap',
              icon: const Icon(Icons.swap_horiz),
              onPressed: () => setState(() {
                    final t = home; home = away; away = t;
                    final o = outHome; outHome = outAway; outAway = o;
                  })),
          Expanded(child: Picker('Away', away, teams, (v) => setState(() => away = v))),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
              child: _outPicker(context, 'Home key out', outHome,
                  (v) => setState(() => outHome = v!))),
          const SizedBox(width: 12),
          Expanded(
              child: _outPicker(context, 'Away key out', outAway,
                  (v) => setState(() => outAway = v!))),
        ]),
        _matchup(context, home!, away!),
        Center(child: ConfidenceBadge(fav)),
        ConfidenceNote(fav),
        WhyThis(_gridReasons(home!, away!, r, log: log)),
        const SizedBox(height: 12),
        ProbBar(home!, r.home, r.home == fav, accent),
        ProbBar('Draw', r.draw, r.draw == fav, accent),
        ProbBar(away!, r.away, r.away == fav, accent),
        const SizedBox(height: 10),
        Text('Expected goals  ${r.lh.toStringAsFixed(2)} – ${r.la.toStringAsFixed(2)}',
            style: TextStyle(color: _muted(context))),
        _chips(context, 'Goals markets', r.goals, accent),
        _chips(context, 'Result & handicap', {
          'Double 1X': rm['1X']!, 'Double X2': rm['X2']!, 'Double 12': rm['12']!,
          'Home -1.5': rm['Home -1.5']!, 'Away -1.5': rm['Away -1.5']!,
          'Home CS': rm['Home CS']!, 'Away CS': rm['Away CS']!,
        }, accent),
        if (counts != null) ...[
          _label(context,
              'Corners (proj ${counts.corners.toStringAsFixed(1)})'),
          MarketChips(counts.cornerO, accent),
          _label(context, 'Cards (proj ${counts.cards.toStringAsFixed(1)})'),
          MarketChips(counts.cardO, accent),
        ],
        _label(context, 'Most likely scores'),
        Text(r.scorelines.map((s) => '${s.key}  ${pct(s.value)}').join('    '),
            style: TextStyle(fontSize: 13, color: _muted(context))),
      ]),
      _card(context, [
        _label(context, 'Recent form (newest first)'),
        _formRow(context, home!, teamForm(log, home!)),
        _formRow(context, away!, teamForm(log, away!)),
        _label(context, 'Head-to-head'),
        ...() {
          final h2h = h2hMeetings(log, home!, away!);
          return h2h.isEmpty
              ? [Text('No recent meetings.', style: TextStyle(color: _muted(context)))]
              : h2h
                  .map((m) => Text(m,
                      style: TextStyle(fontSize: 13, color: _muted(context))))
                  .toList();
        }(),
        const Text('\nForm/H2H shown for context — our tests found H2H adds no '
            'predictive value, so it is not used in the prediction above.',
            style: TextStyle(fontSize: 11)),
      ]),
      _card(context, [
        Builder(builder: (c) {
          final sorted = [...teamMaps]
            ..sort((a, b) => (_d(b['attack']) - _d(b['defence']))
                .compareTo(_d(a['attack']) - _d(a['defence'])));
          return ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: Text('Power ratings — $leagueName',
                style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: _muted(c))),
            children: [
              for (final t in sorted)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    Expanded(child: Text('${t['name']}')),
                    Text(
                        'atk ${_d(t['attack']).toStringAsFixed(2)}   def ${(-_d(t['defence'])).toStringAsFixed(2)}',
                        style: TextStyle(
                            fontSize: 12,
                            color: _muted(c),
                            fontFeatures: const [FontFeature.tabularFigures()])),
                  ]),
                ),
            ],
          );
        }),
      ]),
      _card(context, _fixturesSection(
          context,
          (((widget.data['leagues'] as Map)[nameToCode[leagueName]]
                  as Map)['fixtures'] as List?) ??
              const [],
          accent)),
      const ResponsibleNote(),
    ]));
  }
}

// ------------------------------------------------------ World Cup / UCL (Elo)
class EloTab extends StatefulWidget {
  final Map data;
  final String sportKey;
  final bool defaultNeutral;
  final Future<void> Function() onRefresh;
  const EloTab(this.data, this.sportKey,
      {this.defaultNeutral = true, required this.onRefresh, super.key});
  @override
  State<EloTab> createState() => _EloTabState();
}

class _EloTabState extends State<EloTab> {
  late Map sport = widget.data[widget.sportKey] as Map;
  late List teams = sport['teams'] as List;
  late Map<String, double> elo = _eloMap(teams);
  late List<String> names = _names(teams);
  late String home = names.first;
  late String away = names.length > 1 ? names[1] : names.first;
  late bool neutral = widget.defaultNeutral;
  int outHome = 0, outAway = 0;

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final r = Predict.elo(sport, elo[home]!, elo[away]!, neutral,
        outHome: outHome, outAway: outAway);
    final fav = [r.home, r.draw, r.away].reduce((a, b) => a > b ? a : b);
    final rm = r.result;
    return RefreshIndicator(
        onRefresh: widget.onRefresh,
        child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
      _card(context, [
        Row(children: [
          Expanded(child: Picker('Home', home, names, (v) => setState(() => home = v!))),
          IconButton(
              tooltip: 'Swap',
              icon: const Icon(Icons.swap_horiz),
              onPressed: () => setState(() {
                    final t = home; home = away; away = t;
                    final o = outHome; outHome = outAway; outAway = o;
                  })),
          Expanded(child: Picker('Away', away, names, (v) => setState(() => away = v!))),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
              child: _outPicker(context, 'Home key out', outHome,
                  (v) => setState(() => outHome = v!))),
          const SizedBox(width: 12),
          Expanded(
              child: _outPicker(context, 'Away key out', outAway,
                  (v) => setState(() => outAway = v!))),
        ]),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Neutral venue'),
          value: neutral,
          onChanged: (v) => setState(() => neutral = v),
        ),
        _matchup(context, home, away),
        Center(child: ConfidenceBadge(fav)),
        ConfidenceNote(fav),
        WhyThis(_gridReasons(home, away, r,
            eloH: elo[home], eloA: elo[away], neutral: neutral)),
        const SizedBox(height: 12),
        ProbBar(home, r.home, r.home == fav, accent),
        ProbBar('Draw', r.draw, r.draw == fav, accent),
        ProbBar(away, r.away, r.away == fav, accent),
        const SizedBox(height: 10),
        Text('Expected goals  ${r.lh.toStringAsFixed(2)} – ${r.la.toStringAsFixed(2)}',
            style: TextStyle(color: _muted(context))),
        _chips(context, 'Goals markets', r.goals, accent),
        _chips(context, 'Result & handicap', {
          'Double 1X': rm['1X']!, 'Double X2': rm['X2']!, 'Double 12': rm['12']!,
          'Home -1.5': rm['Home -1.5']!, 'Away -1.5': rm['Away -1.5']!,
        }, accent),
        ..._countsSection(context, widget.data, home, away, widget.sportKey, accent),
        _label(context, 'Most likely scores'),
        Text(r.scorelines.map((s) => '${s.key}  ${pct(s.value)}').join('    '),
            style: TextStyle(fontSize: 13, color: _muted(context))),
        const SizedBox(height: 6),
        Text('Elo  $home ${elo[home]!.round()}  ·  $away ${elo[away]!.round()}',
            style: TextStyle(fontSize: 12, color: _muted(context))),
      ]),
      _card(context, [_eloRatings(context, teams)]),
      _card(context, _fixturesSection(
          context,
          ((widget.data[widget.sportKey] as Map)['fixtures'] as List?) ?? const [],
          accent)),
      const ResponsibleNote(),
    ]));
  }
}

// ------------------------------------------------- Basketball hub (NBA / WNBA)
class BasketballTab extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const BasketballTab(this.data, {required this.onRefresh, super.key});
  @override
  State<BasketballTab> createState() => _BasketballTabState();
}

class _BasketballTabState extends State<BasketballTab> {
  late final List<Map> _leagues = (((widget.data['basketball_leagues'] as List?) ??
          const [{'key': 'nba', 'name': 'NBA'}]))
      .cast<Map>()
      .where((l) => widget.data[l['key']] != null)
      .toList();
  late String _key = _leagues.isNotEmpty ? _leagues.first['key'] as String : 'nba';
  String home = '', away = '';
  int outHome = 0, outAway = 0;

  Map get _lg => widget.data[_key] as Map;
  List get _teams => _lg['teams'] as List;

  @override
  void initState() {
    super.initState();
    _resetTeams();
  }

  void _resetTeams() {
    final n = _names(_teams);
    home = n.first;
    away = n.length > 1 ? n[1] : n.first;
  }

  void _setLeagueByName(String? name) {
    final match = _leagues.firstWhere((l) => l['name'] == name,
        orElse: () => _leagues.first);
    setState(() {
      _key = match['key'] as String;
      outHome = 0;
      outAway = 0;
      _resetTeams();
    });
  }

  /// "Title chances" card — championship % per team (Monte-Carlo from ratings).
  List<Widget> _titleRace(BuildContext c, List<Map> odds, Color accent) {
    final cs = Theme.of(c).colorScheme;
    final top = odds.take(8).toList();
    final maxPct = top.isEmpty ? 1.0 : (top.first['pct'] as num).toDouble();
    return [
      Text('TITLE CHANCES',
          style: TextStyle(
              fontSize: 11, letterSpacing: 1.2, fontWeight: FontWeight.w700,
              color: cs.onSurface.withOpacity(.6))),
      const SizedBox(height: 2),
      Text('Simulated championship odds — if the playoffs were seeded by current rating',
          style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.6), height: 1.35)),
      const SizedBox(height: 12),
      ...top.map((o) {
        final pct = (o['pct'] as num).toDouble();
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            SizedBox(
                width: 130,
                child: Text('${o['name']}',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600))),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(5),
                child: Container(
                  height: 14,
                  color: cs.onSurface.withOpacity(.07),
                  child: FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: (pct / maxPct).clamp(0.02, 1.0),
                    child: Container(color: accent),
                  ),
                ),
              ),
            ),
            SizedBox(
                width: 46,
                child: Text('${(pct * 100).toStringAsFixed(pct >= .1 ? 0 : 1)}%',
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                        fontSize: 12,
                        fontFeatures: [FontFeature.tabularFigures()]))),
          ]),
        );
      }),
    ];
  }

  Widget _exhibitionBanner(BuildContext c) {
    final cs = Theme.of(c).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.5),
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: cs.primary, width: 3)),
      ),
      child: Row(children: [
        Icon(Icons.info_outline, size: 18, color: cs.onSurface.withOpacity(.6)),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            'Exhibition — Summer League rosters are prospects, not full squads, '
            'over just a few games, so treat these as low-confidence.',
            style: TextStyle(fontSize: 12, height: 1.35, color: cs.onSurface.withOpacity(.7)),
          ),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final lg = _lg;
    final elo = _eloMap(_teams);
    final names = _names(_teams);
    if (!names.contains(home)) home = names.first;
    if (!names.contains(away)) away = names.length > 1 ? names[1] : names.first;

    final r = Predict.nba(lg, elo[home]!, elo[away]!, false,
        outHome: outHome, outAway: outAway);
    final fav = r.homeWin > r.awayWin ? r.homeWin : r.awayWin;
    final favName = r.homeWin >= r.awayWin ? home : away;
    final margin = (r.projHome - r.projAway).abs().round();
    final gap = (elo[home]! - elo[away]!).abs().round();
    final reasons = <Reason>[
      Reason(Icons.emoji_events_outlined,
          '$favName is favoured to win at ${pct(fav)}.'),
      if (gap >= 15)
        Reason(Icons.leaderboard_outlined,
            '${elo[home]! >= elo[away]! ? home : away} carries a $gap-point rating edge.')
      else
        Reason(Icons.leaderboard_outlined,
            'The teams are closely rated (within $gap points).'),
      Reason(Icons.scoreboard_outlined,
          'Projected ${r.projHome.round()}–${r.projAway.round()} — about a $margin-point margin.'),
      Reason(Icons.home_outlined, 'Home-court advantage is applied to $home.'),
    ];
    return RefreshIndicator(
        onRefresh: widget.onRefresh,
        child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
      if (lg['exhibition'] == true) _exhibitionBanner(context),
      _card(context, [
        if (_leagues.length > 1) ...[
          Picker('League', _leagues.firstWhere((l) => l['key'] == _key)['name'] as String,
              [for (final l in _leagues) l['name'] as String], _setLeagueByName),
          const SizedBox(height: 12),
        ],
        Row(children: [
          Expanded(child: Picker('Home', home, names, (v) => setState(() => home = v!))),
          IconButton(
              tooltip: 'Swap',
              icon: const Icon(Icons.swap_horiz),
              onPressed: () => setState(() {
                    final t = home; home = away; away = t;
                    final o = outHome; outHome = outAway; outAway = o;
                  })),
          Expanded(child: Picker('Away', away, names, (v) => setState(() => away = v!))),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
              child: _outPicker(context, 'Home key out', outHome,
                  (v) => setState(() => outHome = v!))),
          const SizedBox(width: 12),
          Expanded(
              child: _outPicker(context, 'Away key out', outAway,
                  (v) => setState(() => outAway = v!))),
        ]),
        _matchup(context, home, away),
        Center(child: ConfidenceBadge(fav)),
        ConfidenceNote(fav),
        WhyThis(reasons),
        const SizedBox(height: 12),
        ProbBar(home, r.homeWin, r.homeWin >= r.awayWin, accent),
        ProbBar(away, r.awayWin, r.awayWin > r.homeWin, accent),
        const SizedBox(height: 12),
        Text('Projected score  ${r.projHome.round()} – ${r.projAway.round()}',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        _chips(context, 'Spread (cover)',
            Predict.nbaSpread(lg, elo[home]!, elo[away]!, false,
                outHome: outHome, outAway: outAway),
            accent),
        _chips(context, 'Total points', Predict.totalsAround(lg), accent),
        _chips(context, 'Team totals',
            Predict.teamTotals(lg, elo[home]!, elo[away]!, false, home, away,
                outHome: outHome, outAway: outAway),
            accent),
      ]),
      _card(context, [BeatModelPick(
          home: home, away: away, sport: _key, allowDraw: false,
          modelPick: r.homeWin >= r.awayWin ? 'H' : 'A', accent: accent)]),
      if (((lg['title_odds'] as List?) ?? const []).isNotEmpty)
        _card(context, _titleRace(context, (lg['title_odds'] as List).cast<Map>(), accent)),
      _card(context, [_eloRatings(context, _teams)]),
      _card(context, _fixturesSection(
          context, (lg['fixtures'] as List?) ?? const [], accent)),
      const ResponsibleNote(),
    ]));
  }
}

// ----------------------------------------------------------------- NFL
class NflTab extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const NflTab(this.data, {required this.onRefresh, super.key});
  @override
  State<NflTab> createState() => _NflTabState();
}

class _NflTabState extends State<NflTab> {
  late Map nfl = widget.data['nfl'] as Map;
  late List teams = nfl['teams'] as List;
  late Map<String, double> elo = _eloMap(teams);
  late List<String> names = _names(teams);
  late String home = names.first;
  late String away = names.length > 1 ? names[1] : names.first;
  int outHome = 0, outAway = 0;

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final r = Predict.nfl(nfl, elo[home]!, elo[away]!, false,
        outHome: outHome, outAway: outAway);
    final fav = r.homeWin > r.awayWin ? r.homeWin : r.awayWin;
    final favName = r.homeWin >= r.awayWin ? home : away;
    final margin = (r.projHome - r.projAway).abs().round();
    final gap = (elo[home]! - elo[away]!).abs().round();
    final reasons = <Reason>[
      Reason(Icons.emoji_events_outlined,
          '$favName is favoured to win at ${pct(fav)}.'),
      if (gap >= 15)
        Reason(Icons.leaderboard_outlined,
            '${elo[home]! >= elo[away]! ? home : away} carries a $gap-point rating edge.')
      else
        Reason(Icons.leaderboard_outlined,
            'The teams are closely rated (within $gap points).'),
      Reason(Icons.scoreboard_outlined,
          'Projected ${r.projHome.round()}–${r.projAway.round()} — about a $margin-point margin.'),
      Reason(Icons.home_outlined, 'Home-field advantage is applied to $home.'),
    ];
    return RefreshIndicator(
        onRefresh: widget.onRefresh,
        child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
      _card(context, [
        Row(children: [
          Expanded(child: Picker('Home', home, names, (v) => setState(() => home = v!))),
          IconButton(
              tooltip: 'Swap',
              icon: const Icon(Icons.swap_horiz),
              onPressed: () => setState(() {
                    final t = home; home = away; away = t;
                    final o = outHome; outHome = outAway; outAway = o;
                  })),
          Expanded(child: Picker('Away', away, names, (v) => setState(() => away = v!))),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
              child: _outPicker(context, 'Home key out', outHome,
                  (v) => setState(() => outHome = v!))),
          const SizedBox(width: 12),
          Expanded(
              child: _outPicker(context, 'Away key out', outAway,
                  (v) => setState(() => outAway = v!))),
        ]),
        _matchup(context, home, away),
        Center(child: ConfidenceBadge(fav)),
        ConfidenceNote(fav),
        WhyThis(reasons),
        const SizedBox(height: 12),
        ProbBar(home, r.homeWin, r.homeWin >= r.awayWin, accent),
        ProbBar(away, r.awayWin, r.awayWin > r.homeWin, accent),
        const SizedBox(height: 12),
        Text('Projected score  ${r.projHome.round()} – ${r.projAway.round()}',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        _chips(context, 'Spread (cover)',
            Predict.nflSpread(nfl, elo[home]!, elo[away]!, false,
                outHome: outHome, outAway: outAway),
            accent),
        _chips(context, 'Total points', Predict.nflTotals(nfl), accent),
      ]),
      _card(context, [BeatModelPick(
          home: home, away: away, sport: 'nfl', allowDraw: false,
          modelPick: r.homeWin >= r.awayWin ? 'H' : 'A', accent: accent)]),
      _card(context, [_eloRatings(context, teams)]),
      _card(context, _fixturesSection(
          context,
          ((widget.data['nfl'] as Map)['fixtures'] as List?) ?? const [],
          accent)),
      const ResponsibleNote(),
    ]));
  }
}

// ----------------------------------------------------------------- Tennis
class TennisTab extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const TennisTab(this.data, {required this.onRefresh, super.key});
  @override
  State<TennisTab> createState() => _TennisTabState();
}

class _TennisTabState extends State<TennisTab> {
  late Map tennis = widget.data['tennis'] as Map;
  late List players = tennis['players'] as List;
  late Map<String, Map> byName = {for (final p in players) p['name'] as String: p as Map};
  late List<String> names = byName.keys.toList()..sort();
  late String a = (players.first)['name'] as String;
  late String b = (players.length > 1 ? players[1] : players.first)['name'] as String;
  String surface = 'Hard';

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final pa = Predict.tennis(tennis, byName[a]!, byName[b]!, surface);
    final fav = pa >= .5 ? pa : 1 - pa;
    final favName = pa >= .5 ? a : b;
    final eloA = _d(byName[a]!['elo']);
    final eloB = _d(byName[b]!['elo']);
    final gap = (eloA - eloB).abs().round();
    final tennisReasons = <Reason>[
      Reason(Icons.emoji_events_outlined, '$favName is favoured at ${pct(fav)}.'),
      if (gap >= 15)
        Reason(Icons.leaderboard_outlined,
            '${eloA >= eloB ? a : b} has the higher rating — a $gap-point edge.')
      else
        Reason(Icons.leaderboard_outlined,
            'Closely rated players (within $gap points).'),
      Reason(Icons.sports_tennis_outlined,
          'On $surface, ratings are surface-weighted — form on this surface counts more.'),
    ];
    return RefreshIndicator(
        onRefresh: widget.onRefresh,
        child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
      _card(context, [
        Row(children: [
          Expanded(child: Picker('Player A', a, names, (v) => setState(() => a = v!))),
          const SizedBox(width: 12),
          Expanded(child: Picker('Player B', b, names, (v) => setState(() => b = v!))),
        ]),
        const SizedBox(height: 12),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'Hard', label: Text('Hard')),
            ButtonSegment(value: 'Clay', label: Text('Clay')),
            ButtonSegment(value: 'Grass', label: Text('Grass')),
          ],
          selected: {surface},
          onSelectionChanged: (s) => setState(() => surface = s.first),
        ),
        _matchup(context, a, b),
        Center(child: ConfidenceBadge(fav)),
        ConfidenceNote(fav),
        WhyThis(tennisReasons),
        const SizedBox(height: 12),
        ProbBar(a, pa, pa >= .5, accent),
        ProbBar(b, 1 - pa, pa < .5, accent),
      ]),
      _card(context, [_eloRatings(context, players)]),
      const ResponsibleNote(),
    ]));
  }
}
