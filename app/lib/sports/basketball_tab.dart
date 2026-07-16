part of '../predictors.dart';

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
          modelPick: r.homeWin >= r.awayWin ? 'H' : 'A',
          modelProb: fav, accent: accent)]),
      if (((lg['title_odds'] as List?) ?? const []).isNotEmpty)
        _card(context, _titleRace(context, (lg['title_odds'] as List).cast<Map>(), accent)),
      _card(context, [_eloRatings(context, _teams)]),
      _card(context, _fixturesSection(
          context, (lg['fixtures'] as List?) ?? const [], accent)),
      const ResponsibleNote(),
    ]));
  }
}

