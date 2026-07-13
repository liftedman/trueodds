part of '../predictors.dart';

// ----------------------------------------------------------------- Tennis
class TennisTab extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const TennisTab(this.data, {required this.onRefresh, super.key});
  @override
  State<TennisTab> createState() => _TennisTabState();
}

class _TennisTabState extends State<TennisTab> {
  late final List<Map> _tours = (((widget.data['tennis_tours'] as List?) ??
          const [{'key': 'tennis', 'name': 'ATP'}]))
      .cast<Map>()
      .where((t) => widget.data[t['key']] != null)
      .toList();
  late String _key = _tours.isNotEmpty ? _tours.first['key'] as String : 'tennis';
  String a = '', b = '';
  String surface = 'Hard';

  Map get tennis => widget.data[_key] as Map;
  List get players => tennis['players'] as List;
  Map<String, Map> get byName =>
      {for (final p in players) p['name'] as String: p as Map};
  List<String> get names => byName.keys.toList()..sort();

  @override
  void initState() {
    super.initState();
    _resetPlayers();
  }

  void _resetPlayers() {
    final n = names;
    a = n.first;
    b = n.length > 1 ? n[1] : n.first;
  }

  void _setTourByName(String? nm) {
    final m = _tours.firstWhere((t) => t['name'] == nm, orElse: () => _tours.first);
    setState(() {
      _key = m['key'] as String;
      _resetPlayers();
    });
  }

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final nm = names;
    if (!nm.contains(a)) a = nm.first;
    if (!nm.contains(b)) b = nm.length > 1 ? nm[1] : nm.first;
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
        if (_tours.length > 1) ...[
          Picker('Tour', _tours.firstWhere((t) => t['key'] == _key)['name'] as String,
              [for (final t in _tours) t['name'] as String], _setTourByName),
          const SizedBox(height: 12),
        ],
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
