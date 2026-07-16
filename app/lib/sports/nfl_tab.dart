part of '../predictors.dart';

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
          modelPick: r.homeWin >= r.awayWin ? 'H' : 'A',
          modelProb: fav, accent: accent)]),
      _card(context, [_eloRatings(context, teams)]),
      _card(context, _fixturesSection(
          context,
          ((widget.data['nfl'] as Map)['fixtures'] as List?) ?? const [],
          accent)),
      const ResponsibleNote(),
    ]));
  }
}

