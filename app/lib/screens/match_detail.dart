import 'package:flutter/material.dart';
import 'dart:math';
import 'package:sports_model_app/services/beat_model.dart';
import 'package:sports_model_app/services/favorites.dart';
import 'package:sports_model_app/widgets/live_prob.dart';
import 'package:sports_model_app/models/predict.dart';
import 'package:sports_model_app/widgets/team_avatar.dart';
import 'package:sports_model_app/widgets/theme.dart';
import 'package:sports_model_app/widgets/trust.dart';
import 'package:sports_model_app/widgets/widgets.dart';

double _d(dynamic v) => (v as num).toDouble();

Map? _findClubLeague(Map data, String home, String away) {
  for (final lg in (data['leagues'] as Map? ?? {}).values) {
    final names = (lg['teams'] as List).map((t) => t['name']).toSet();
    if (names.contains(home) && names.contains(away)) return lg as Map;
  }
  return null;
}

Map<String, double> _eloMap(List teams) =>
    {for (final t in teams) t['name'] as String: _d(t['elo'])};

/// Full prediction breakdown for one fixture.
class MatchDetailScreen extends StatelessWidget {
  final Map data;
  final String sportKey; // clubs / wc / cl / nba
  final String home, away;
  final Map? fixture;
  const MatchDetailScreen(
      {required this.data,
      required this.sportKey,
      required this.home,
      required this.away,
      this.fixture,
      super.key});

  @override
  Widget build(BuildContext context) {
    final accent = AppTheme.sportAccent[sportKey] ?? const Color(0xFF0EA5A4);
    return Theme(
      data: Theme.of(context).copyWith(
          colorScheme: Theme.of(context).colorScheme.copyWith(primary: accent)),
      child: Scaffold(
        appBar: AppBar(title: Text('$home v $away')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _header(context),
            const SizedBox(height: 8),
            Row(children: [
              TeamAvatar(home, size: 30),
              const SizedBox(width: 8),
              Expanded(child: Text(home, overflow: TextOverflow.ellipsis)),
              FavStar(sportKey, home),
              const SizedBox(width: 8),
              TeamAvatar(away, size: 30),
              const SizedBox(width: 8),
              Expanded(child: Text(away, overflow: TextOverflow.ellipsis)),
              FavStar(sportKey, away),
            ]),
            ..._body(context, accent),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext c) {
    final muted = Theme.of(c).colorScheme.onSurface.withOpacity(.6);
    final f = fixture;
    if (f == null) return const SizedBox.shrink();
    final live = f['live'] == true;
    return Row(children: [
      Icon(live ? Icons.podcasts : Icons.schedule, size: 16,
          color: live ? const Color(0xFFE5484D) : muted),
      const SizedBox(width: 6),
      Text(
        live
            ? '● LIVE${f['score'] != null ? '  ${f['score']}' : ''}'
            : '${f['date']}  ·  ${f['time']}',
        style: TextStyle(
            color: live ? const Color(0xFFE5484D) : muted,
            fontWeight: live ? FontWeight.w700 : FontWeight.normal),
      ),
    ]);
  }

  List<Widget> _body(BuildContext c, Color accent) {
    const basketball = {'nba', 'wnba', 'summer', 'nbl', 'ncaam', 'ncaaw'};
    if (basketball.contains(sportKey)) return _basketball(c, accent);
    if (sportKey == 'nfl') return _nfl(c, accent);
    if (sportKey == 'clubs') return _clubs(c, accent);
    return _elo(c, accent); // wc / cl
  }

  /// Approx minutes played, from the UTC kickoff (with a rough half-time gap).
  int? _liveMinute() {
    final f = fixture;
    if (f == null || f['live'] != true) return null;
    final ko = DateTime.tryParse((f['utc'] as String?) ?? '');
    if (ko == null) return null;
    var mins = DateTime.now().toUtc().difference(ko.toUtc()).inMinutes;
    if (mins < 0) return null;
    if (mins > 45 && mins <= 60) {
      mins = 45; // half-time plateau
    } else if (mins > 60) {
      mins = mins - 15; // discount the break once the second half is on
    }
    return mins.clamp(0, 90);
  }

  (int, int)? _parseScore() {
    final s = fixture?['score'] as String?;
    if (s == null) return null;
    final p = s.split('-');
    if (p.length != 2) return null;
    final h = int.tryParse(p[0].trim()), a = int.tryParse(p[1].trim());
    if (h == null || a == null) return null;
    return (h, a);
  }

  /// The live win-probability block, or null if the match isn't live / lacks data.
  Widget? _liveWidget(Color accent, GridResult r) {
    final minute = _liveMinute();
    final score = _parseScore();
    if (minute == null || score == null) return null;
    return LiveWinProbability(
      home: home,
      away: away,
      lh: r.lh,
      la: r.la,
      preHome: r.home,
      preDraw: r.draw,
      preAway: r.away,
      homeGoals: score.$1,
      awayGoals: score.$2,
      minute: minute,
      accent: accent,
    );
  }

  // ---- football grid (clubs / wc / cl) shared renderer ----
  List<Widget> _grid(BuildContext c, Color accent, GridResult r,
      {List? clubLog, Map? hMap, Map? aMap, List<Reason> reasons = const []}) {
    final fav = [r.home, r.draw, r.away].reduce((a, b) => a > b ? a : b);
    final rm = r.result;
    final counts = (hMap != null && aMap != null) ? clubCounts(hMap, aMap) : null;
    final live = _liveWidget(accent, r);
    return [
      if (live != null) live,
      if (live != null) _label(c, 'Pre-match model'),
      Center(child: ConfidenceBadge(fav)),
      ConfidenceNote(fav),
      WhyThis(reasons),
      const SizedBox(height: 16),
      ProbBar(home, r.home, r.home == fav, accent),
      ProbBar('Draw', r.draw, r.draw == fav, accent),
      ProbBar(away, r.away, r.away == fav, accent),
      const SizedBox(height: 10),
      _muted(c, 'Expected goals  ${r.lh.toStringAsFixed(2)} – ${r.la.toStringAsFixed(2)}'),
      _label(c, 'Goals markets'),
      MarketChips(r.goals, accent),
      _label(c, 'Result & handicap'),
      MarketChips({
        'Double 1X': rm['1X']!, 'Double X2': rm['X2']!, 'Double 12': rm['12']!,
        'Home -1.5': rm['Home -1.5']!, 'Away -1.5': rm['Away -1.5']!,
        'Home CS': rm['Home CS']!, 'Away CS': rm['Away CS']!,
      }, accent),
      if (counts != null) ...[
        _label(c, 'Corners (proj ${counts.corners.toStringAsFixed(1)})'),
        MarketChips(counts.cornerO, accent),
        _label(c, 'Cards (proj ${counts.cards.toStringAsFixed(1)})'),
        MarketChips(counts.cardO, accent),
      ],
      _label(c, 'Most likely scores'),
      _muted(c, r.scorelines.map((s) => '${s.key}  ${pct(s.value)}').join('    ')),
      if (clubLog != null) ...[
        _label(c, 'Recent form'),
        _form(c, home, teamForm(clubLog, home)),
        _form(c, away, teamForm(clubLog, away)),
      ],
      BeatModelPick(
        home: home,
        away: away,
        sport: sportKey,
        modelPick: r.home >= r.draw && r.home >= r.away
            ? 'H'
            : (r.away >= r.draw ? 'A' : 'D'),
        accent: accent,
      ),
      const ResponsibleNote(),
    ];
  }

  List<Widget> _clubs(BuildContext c, Color accent) {
    final lg = _findClubLeague(data, home, away);
    if (lg == null) return [_muted(c, 'Team ratings unavailable for this match.')];
    final teams = lg['teams'] as List;
    Map tm(String n) => teams.firstWhere((t) => t['name'] == n, orElse: () => {});
    final r = Predict.club(lg, home, away);
    final log = lg['log'] as List?;
    return _grid(c, accent, r,
        clubLog: log,
        hMap: tm(home),
        aMap: tm(away),
        reasons: _gridReasons(r, log: log, neutral: false));
  }

  List<Widget> _elo(BuildContext c, Color accent) {
    final sport = data[sportKey] as Map;
    final elo = _eloMap(sport['teams'] as List);
    final eloH = elo[home] ?? 1500, eloA = elo[away] ?? 1500;
    final neutral = sportKey == 'wc';
    final r = Predict.elo(sport, eloH, eloA, neutral);
    return _grid(c, accent, r,
        reasons: _gridReasons(r, eloH: eloH, eloA: eloA, neutral: neutral));
  }

  /// Plain-language reasons behind a football/Elo grid prediction.
  List<Reason> _gridReasons(GridResult r,
      {List? log, double? eloH, double? eloA, bool neutral = false}) {
    final out = <Reason>[];
    final fav = [r.home, r.draw, r.away].reduce(max);
    final favName = fav == r.home ? home : (fav == r.away ? away : 'A draw');
    out.add(Reason(Icons.emoji_events_outlined,
        '$favName is the most likely outcome at ${pct(fav)}.'));

    if (eloH != null && eloA != null) {
      final gap = (eloH - eloA).abs().round();
      if (gap >= 15) {
        final stronger = eloH >= eloA ? home : away;
        out.add(Reason(Icons.leaderboard_outlined,
            '$stronger is rated $gap Elo points higher — the stronger side on paper.'));
      } else {
        out.add(Reason(Icons.leaderboard_outlined,
            'The two sides are closely rated (within $gap Elo points).'));
      }
    }

    out.add(Reason(Icons.sports_soccer_outlined,
        'Expected goals: ${r.lh.toStringAsFixed(2)} for $home, ${r.la.toStringAsFixed(2)} for $away.'));

    if (neutral) {
      out.add(const Reason(Icons.flag_outlined,
          'Neutral venue — no home advantage applied.'));
    } else {
      out.add(Reason(Icons.home_outlined,
          'Home advantage is built into $home\'s expected goals.'));
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

  /// Live in-play win-probability block for a basketball game, or null.
  Widget? _bballLive(BuildContext c, Color accent, Map nba, double eloH, double eloA) {
    final f = fixture;
    if (f == null || f['live'] != true || f['frac_left'] == null) return null;
    final sc = _parseScore();
    if (sc == null) return null;
    final frac = (f['frac_left'] as num).toDouble();
    final lp = Predict.inPlayBasketball(nba, eloH, eloA, sc.$1, sc.$2, frac);
    final curve = Predict.inPlayBasketballCurve(nba, eloH, eloA, sc.$1, sc.$2, frac);
    final cs = Theme.of(c).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFE5484D).withOpacity(.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5484D).withOpacity(.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Text('● LIVE',
              style: TextStyle(
                  color: Color(0xFFE5484D), fontWeight: FontWeight.w800, fontSize: 13)),
          const SizedBox(width: 8),
          Text('${f['status'] ?? ''}',
              style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.6))),
          const Spacer(),
          Text('${sc.$1} – ${sc.$2}',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
        ]),
        const SizedBox(height: 4),
        Text('Live win probability — updates with the score and the clock',
            style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.6))),
        const SizedBox(height: 10),
        ProbBar(home, lp.home, lp.home >= lp.away, accent),
        ProbBar(away, lp.away, lp.away > lp.home, accent),
        const SizedBox(height: 12),
        Row(children: [
          Text('If lead holds',
              style: TextStyle(fontSize: 11, color: cs.onSurface.withOpacity(.6))),
          const SizedBox(width: 10),
          Expanded(child: Sparkline(curve, accent)),
          const SizedBox(width: 8),
          Text('Final', style: TextStyle(fontSize: 11, color: cs.onSurface.withOpacity(.6))),
        ]),
      ]),
    );
  }

  List<Widget> _basketball(BuildContext c, Color accent) {
    final nba = data[sportKey] as Map;
    final elo = _eloMap(nba['teams'] as List);
    final eloH = elo[home] ?? 1500, eloA = elo[away] ?? 1500;
    final r = Predict.nba(nba, eloH, eloA, false);
    final live = _bballLive(c, accent, nba, eloH, eloA);
    final log = nba['log'] as List?;
    final fav = r.homeWin > r.awayWin ? r.homeWin : r.awayWin;
    final favName = r.homeWin >= r.awayWin ? home : away;
    final margin = (r.projHome - r.projAway).abs().round();
    final gap = (eloH - eloA).abs().round();
    final reasons = <Reason>[
      Reason(Icons.emoji_events_outlined,
          '$favName is favoured to win at ${pct(fav)}.'),
      if (gap >= 15)
        Reason(Icons.leaderboard_outlined,
            '${eloH >= eloA ? home : away} carries a $gap-point rating edge.')
      else
        Reason(Icons.leaderboard_outlined,
            'The teams are closely rated (within $gap points).'),
      Reason(Icons.scoreboard_outlined,
          'Projected ${r.projHome.round()}–${r.projAway.round()} — about a $margin-point margin.'),
      Reason(Icons.home_outlined, 'Home-court advantage is applied to $home.'),
    ];
    return [
      if (live != null) live,
      if (live != null) _label(c, 'Pre-game model'),
      Center(child: ConfidenceBadge(fav)),
      ConfidenceNote(fav),
      WhyThis(reasons),
      const SizedBox(height: 16),
      ProbBar(home, r.homeWin, r.homeWin >= r.awayWin, accent),
      ProbBar(away, r.awayWin, r.awayWin > r.homeWin, accent),
      const SizedBox(height: 12),
      Text('Projected score  ${r.projHome.round()} – ${r.projAway.round()}',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
      _label(c, 'Spread (cover)'),
      MarketChips(Predict.nbaSpread(nba, eloH, eloA, false), accent),
      _label(c, 'Total points'),
      MarketChips(Predict.totalsAround(nba), accent),
      _label(c, 'Team totals'),
      MarketChips(
          Predict.teamTotals(nba, eloH, eloA, false, home, away), accent),
      if (log != null && log.isNotEmpty) ...[
        _label(c, 'Recent form'),
        _form(c, home, teamForm(log, home)),
        _form(c, away, teamForm(log, away)),
        _label(c, 'Recent meetings'),
        ...() {
          final h2h = h2hMeetings(log, home, away);
          return h2h.isEmpty
              ? [_muted(c, 'No recent meetings.')]
              : h2h.map((m) => _muted(c, m)).toList();
        }(),
        const Text(
            '\nContext only — head-to-head has no predictive value in our '
            'tests, so it doesn\'t affect the prediction above.',
            style: TextStyle(fontSize: 11)),
      ],
      BeatModelPick(
        home: home,
        away: away,
        sport: sportKey,
        allowDraw: false,
        modelPick: r.homeWin >= r.awayWin ? 'H' : 'A',
        accent: accent,
      ),
      const ResponsibleNote(),
    ];
  }

  List<Widget> _nfl(BuildContext c, Color accent) {
    final nfl = data['nfl'] as Map;
    final elo = _eloMap(nfl['teams'] as List);
    final eloH = elo[home] ?? 1500, eloA = elo[away] ?? 1500;
    final r = Predict.nfl(nfl, eloH, eloA, false);
    final fav = r.homeWin > r.awayWin ? r.homeWin : r.awayWin;
    final favName = r.homeWin >= r.awayWin ? home : away;
    final margin = (r.projHome - r.projAway).abs().round();
    final gap = (eloH - eloA).abs().round();
    final reasons = <Reason>[
      Reason(Icons.emoji_events_outlined,
          '$favName is favoured to win at ${pct(fav)}.'),
      if (gap >= 15)
        Reason(Icons.leaderboard_outlined,
            '${eloH >= eloA ? home : away} carries a $gap-point rating edge.')
      else
        Reason(Icons.leaderboard_outlined,
            'The teams are closely rated (within $gap points).'),
      Reason(Icons.scoreboard_outlined,
          'Projected ${r.projHome.round()}–${r.projAway.round()} — about a $margin-point margin.'),
      Reason(Icons.home_outlined, 'Home-field advantage is applied to $home.'),
    ];
    return [
      Center(child: ConfidenceBadge(fav)),
      ConfidenceNote(fav),
      WhyThis(reasons),
      const SizedBox(height: 16),
      ProbBar(home, r.homeWin, r.homeWin >= r.awayWin, accent),
      ProbBar(away, r.awayWin, r.awayWin > r.homeWin, accent),
      const SizedBox(height: 12),
      Text('Projected score  ${r.projHome.round()} – ${r.projAway.round()}',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
      _label(c, 'Spread (cover)'),
      MarketChips(Predict.nflSpread(nfl, eloH, eloA, false), accent),
      _label(c, 'Total points'),
      MarketChips(Predict.nflTotals(nfl), accent),
      BeatModelPick(
        home: home,
        away: away,
        sport: 'nfl',
        allowDraw: false,
        modelPick: r.homeWin >= r.awayWin ? 'H' : 'A',
        accent: accent,
      ),
      const ResponsibleNote(),
    ];
  }

  Widget _label(BuildContext c, String t) => Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 6),
        child: Text(t.toUpperCase(),
            style: TextStyle(
                fontSize: 11,
                letterSpacing: 1.2,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
      );

  Widget _muted(BuildContext c, String t) => Text(t,
      style: TextStyle(color: Theme.of(c).colorScheme.onSurface.withOpacity(.6)));

  Widget _form(BuildContext c, String name, List<String> form) {
    Color col(String r) => r == 'W'
        ? AppTheme.hi
        : r == 'D'
            ? AppTheme.lo
            : const Color(0xFF6E4A4A);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(width: 120, child: Text(name, overflow: TextOverflow.ellipsis)),
        if (form.isEmpty)
          _muted(c, '—')
        else
          ...form.map((r) => Container(
                width: 22, height: 22, margin: const EdgeInsets.only(right: 5),
                decoration: BoxDecoration(
                    color: col(r), borderRadius: BorderRadius.circular(5)),
                child: Center(
                    child: Text(r,
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white))),
              )),
      ]),
    );
  }
}
