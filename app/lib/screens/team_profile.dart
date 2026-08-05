import 'package:flutter/material.dart';
import 'package:sports_model_app/models/predict.dart';
import 'package:sports_model_app/screens/match_detail.dart';
import 'package:sports_model_app/services/favorites.dart';
import 'package:sports_model_app/widgets/team_avatar.dart';
import 'package:sports_model_app/widgets/theme.dart';
import 'package:sports_model_app/widgets/widgets.dart';

/// A team/player page reached from search: rating + rank, recent form, a
/// prominent "next match" shortcut, and their upcoming fixtures (each opening
/// the full prediction). Works year-round — even with no games scheduled.
class TeamProfileScreen extends StatelessWidget {
  final Map data;
  final String sportKey;
  final String team;
  const TeamProfileScreen(this.data, this.sportKey, this.team, {super.key});

  // ---- data helpers -------------------------------------------------------

  /// For clubs, the league (of the 12) that contains this team.
  Map? _clubLeague() {
    for (final lg in (data['leagues'] as Map? ?? const {}).values) {
      final names = (lg['teams'] as List).map((t) => t['name']).toSet();
      if (names.contains(team)) return lg as Map;
    }
    return null;
  }

  /// The team's own upcoming/live fixtures across the sport.
  List _fixtures() {
    final out = [];
    void scan(List? fx) {
      if (fx == null) return;
      for (final f in fx) {
        if (f['home'] == team || f['away'] == team) out.add(f);
      }
    }

    if (sportKey == 'clubs') {
      (data['leagues'] as Map?)
          ?.forEach((_, lg) => scan(lg['fixtures'] as List?));
    } else {
      final sp = data[sportKey];
      if (sp is Map) scan(sp['fixtures'] as List?);
    }
    return out;
  }

  List<String> _form() {
    List? log;
    if (sportKey == 'clubs') {
      log = _clubLeague()?['log'] as List?;
    } else {
      log = (data[sportKey] as Map?)?['log'] as List?;
    }
    if (log == null) return const [];
    return teamForm(log, team, 6);
  }

  /// (headline rating, rank line) — shape depends on the sport's model.
  (String, String?)? _rating() {
    if (sportKey == 'clubs') {
      final lg = _clubLeague();
      if (lg == null) return null;
      final teams = (lg['teams'] as List).cast<Map>();
      final me = teams.firstWhere((t) => t['name'] == team, orElse: () => {});
      if (me.isEmpty || me['attack'] == null) return null;
      double net(Map t) =>
          (t['attack'] as num).toDouble() - (t['defence'] as num).toDouble();
      final ranked = [...teams]..sort((a, b) => net(b).compareTo(net(a)));
      final rank = ranked.indexWhere((t) => t['name'] == team) + 1;
      return (
        'Attack ${(me['attack'] as num).toStringAsFixed(2)}  ·  '
            'Defence ${(me['defence'] as num).toStringAsFixed(2)}',
        '#$rank of ${teams.length} in ${lg['name']}'
      );
    }
    // Elo-rated sports (World Cup, UCL, NBA) and tennis players.
    final sp = data[sportKey];
    if (sp is! Map) return null;
    final teams = ((sp['teams'] ?? sp['players']) as List?)?.cast<Map>();
    if (teams == null) return null;
    final me = teams.firstWhere((t) => t['name'] == team, orElse: () => {});
    final elo = me['elo'] as num?;
    if (elo == null) return null;
    final ranked = [...teams]
      ..sort((a, b) => (b['elo'] as num).compareTo(a['elo'] as num));
    final rank = ranked.indexWhere((t) => t['name'] == team) + 1;
    return ('Elo ${elo.round()}', '#$rank of ${teams.length}');
  }

  void _openMatch(BuildContext c, Map f) {
    Navigator.of(c).push(MaterialPageRoute(
        builder: (_) => MatchDetailScreen(
              data: data,
              sportKey: sportKey,
              home: f['home'] as String,
              away: f['away'] as String,
              fixture: f,
            )));
  }

  // ---- ui -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final accent = AppTheme.sportAccent[sportKey] ?? const Color(0xFF0EA5A4);
    final fixtures = _fixtures();
    final form = _form();
    final rating = _rating();

    return Theme(
      data: Theme.of(context).copyWith(
          colorScheme:
              Theme.of(context).colorScheme.copyWith(primary: accent)),
      child: Scaffold(
        appBar: AppBar(
          title: Text(team),
          actions: [FavStar(sportKey, team), const SizedBox(width: 6)],
        ),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            _header(context, rating, accent),
            const SizedBox(height: 18),
            _followButton(context, accent),
            if (fixtures.isNotEmpty) ...[
              const SizedBox(height: 12),
              _nextMatch(context, fixtures.first, accent),
            ],
            if (form.isNotEmpty) ...[
              const SizedBox(height: 24),
              _sectionTitle(context, 'Recent form'),
              const SizedBox(height: 10),
              _formRow(context, form),
            ],
            const SizedBox(height: 24),
            _sectionTitle(context, 'Upcoming fixtures'),
            const SizedBox(height: 6),
            if (fixtures.isEmpty)
              Text('No upcoming fixtures — off-season or none scheduled yet.',
                  style: TextStyle(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withOpacity(.6)))
            else
              FixturesList(fixtures, accent, onOpen: _openMatch),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext c, (String, String?)? rating, Color accent) {
    final cs = Theme.of(c).colorScheme;
    return Row(children: [
      TeamAvatar(team, size: 56),
      const SizedBox(width: 14),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(team,
              style: const TextStyle(
                  fontSize: 22, fontWeight: FontWeight.w800, height: 1.1)),
          const SizedBox(height: 4),
          if (rating != null) ...[
            Text(rating.$1,
                style: TextStyle(
                    fontSize: 13,
                    color: cs.onSurface.withOpacity(.7),
                    fontFeatures: const [FontFeature.tabularFigures()])),
            if (rating.$2 != null)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(rating.$2!,
                    style: TextStyle(
                        fontSize: 12, color: cs.onSurface.withOpacity(.5))),
              ),
          ] else
            Text('Ratings unavailable',
                style:
                    TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.5))),
        ]),
      ),
    ]);
  }

  Widget _followButton(BuildContext c, Color accent) => ListenableBuilder(
        listenable: favorites,
        builder: (c, _) {
          final on = favorites.isFav(sportKey, team);
          return SizedBox(
            width: double.infinity,
            child: on
                ? OutlinedButton.icon(
                    onPressed: () => favorites.toggle(sportKey, team),
                    icon: const Icon(Icons.star, size: 18),
                    label: const Text('Following'),
                    style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(46)),
                  )
                : FilledButton.icon(
                    onPressed: () => favorites.toggle(sportKey, team),
                    icon: const Icon(Icons.star_border, size: 18),
                    label: const Text('Follow'),
                    style: FilledButton.styleFrom(
                        backgroundColor: accent,
                        foregroundColor: Colors.white,
                        minimumSize: const Size.fromHeight(46)),
                  ),
          );
        },
      );

  Widget _nextMatch(BuildContext c, Map f, Color accent) {
    final cs = Theme.of(c).colorScheme;
    final opp = f['home'] == team ? f['away'] : f['home'];
    final live = f['live'] == true;
    final when = live
        ? '● LIVE${f['score'] != null ? '  ${f['score']}' : ''}'
        : '${f['date'] ?? ''}  ·  ${f['time'] ?? ''}';
    return Material(
      color: accent.withOpacity(.12),
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => _openMatch(c, f),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            Icon(live ? Icons.podcasts : Icons.sports, color: accent),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(live ? 'Live now' : 'Next match',
                        style: TextStyle(
                            fontSize: 11,
                            letterSpacing: 1,
                            fontWeight: FontWeight.w700,
                            color: accent)),
                    const SizedBox(height: 2),
                    Text('vs $opp',
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w700)),
                    Text(when,
                        style: TextStyle(
                            fontSize: 12,
                            color: cs.onSurface.withOpacity(.6))),
                  ]),
            ),
            Icon(Icons.chevron_right, color: cs.onSurface.withOpacity(.5)),
          ]),
        ),
      ),
    );
  }

  Widget _formRow(BuildContext c, List<String> form) {
    Color col(String r) => r == 'W'
        ? AppTheme.hi
        : (r == 'D' ? AppTheme.med : const Color(0xFFE5484D));
    return Row(
      children: [
        for (final r in form)
          Container(
            margin: const EdgeInsets.only(right: 8),
            width: 30,
            height: 30,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: col(r).withOpacity(.16),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: col(r).withOpacity(.5)),
            ),
            child: Text(r,
                style: TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w800, color: col(r))),
          ),
        Text('newest',
            style: TextStyle(
                fontSize: 11,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.4))),
      ],
    );
  }

  Widget _sectionTitle(BuildContext c, String t) => Text(t,
      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800));
}
