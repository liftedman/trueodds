part of '../predictors.dart';

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

