part of '../predictors.dart';

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

