import 'package:flutter/material.dart';
import 'package:sports_model_app/services/beat_model.dart';
import 'package:sports_model_app/screens/beat_model_screen.dart';
import 'package:sports_model_app/widgets/brand.dart';
import 'package:sports_model_app/services/favorites.dart';
import 'package:sports_model_app/screens/match_detail.dart';
import 'package:sports_model_app/widgets/team_avatar.dart';
import 'package:sports_model_app/widgets/theme.dart';

/// The "Today" feed — live + upcoming matches aggregated across every sport.
class TodayScreen extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const TodayScreen(this.data, this.onRefresh, {super.key});
  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  bool _soonOnly = false; // narrow the upcoming list to the next 7 days

  List<Map> _collect() {
    final data = widget.data;
    final out = <Map>[];
    void add(String key, List? fx) {
      for (final f in (fx ?? const [])) out.add({'key': key, 'fx': f as Map});
    }
    (data['leagues'] as Map?)?.forEach((_, lg) => add('clubs', lg['fixtures'] as List?));
    add('wc', (data['wc'] as Map?)?['fixtures'] as List?);
    add('cl', (data['cl'] as Map?)?['fixtures'] as List?);
    add('nba', (data['nba'] as Map?)?['fixtures'] as List?);
    add('wnba', (data['wnba'] as Map?)?['fixtures'] as List?);
    add('summer', (data['summer'] as Map?)?['fixtures'] as List?);
    add('nbl', (data['nbl'] as Map?)?['fixtures'] as List?);
    add('ncaam', (data['ncaam'] as Map?)?['fixtures'] as List?);
    add('nfl', (data['nfl'] as Map?)?['fixtures'] as List?);
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final all = _collect();
    final live = all.where((e) => e['fx']['live'] == true).toList();
    final upcomingAll = all.where((e) => e['fx']['live'] != true).toList()
      ..sort((a, b) => '${a['fx']['date']} ${a['fx']['time']}'
          .compareTo('${b['fx']['date']} ${b['fx']['time']}'));
    // "Soon" = kicks off within the next 7 days.
    final cutoff = DateTime.now().add(const Duration(days: 7));
    bool soon(Map e) {
      final d = DateTime.tryParse('${e['fx']['date']}');
      return d != null && d.isBefore(cutoff);
    }
    final upcoming = _soonOnly ? upcomingAll.where(soon).toList() : upcomingAll;
    final soonCount = upcomingAll.where(soon).length;
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);

    return ListenableBuilder(
      listenable: favorites,
      builder: (context, _) {
        final mine = all
            .where((e) =>
                favorites.contains(e['fx']['home']) ||
                favorites.contains(e['fx']['away']))
            .toList();
        return RefreshIndicator(
          onRefresh: widget.onRefresh,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
              const Text('Today',
                  style: TextStyle(
                      fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -.5)),
              Text('Live & upcoming across every sport',
                  style: TextStyle(color: muted)),
              const SizedBox(height: 16),
              _beatModelCard(context),
              const SizedBox(height: 16),
              if (mine.isNotEmpty) ...[
                _sectionLabel(context, '★ Your teams', const Color(0xFFE8A33D)),
                ...mine.map((e) => _MatchTile(widget.data, e['key'], e['fx'])),
                const SizedBox(height: 16),
              ],
              if (live.isNotEmpty) ...[
                _sectionLabel(context, '● Live now', const Color(0xFFE5484D)),
                ...live.map((e) => _MatchTile(widget.data, e['key'], e['fx'])),
                const SizedBox(height: 16),
              ],
              _rangeChips(context, soonCount),
              const SizedBox(height: 8),
              if (upcoming.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Center(
                      child: Text(
                          _soonOnly
                              ? 'Nothing in the next 7 days — switch to All to see what\'s coming.'
                              : 'No matches scheduled right now.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: muted))),
                )
              else
                ..._groupedUpcoming(context, upcoming, muted),
            ],
          ),
        );
      },
    );
  }

  /// "Soon (7 days) / All" toggle for the upcoming list.
  Widget _rangeChips(BuildContext context, int soonCount) => Row(children: [
        ChoiceChip(
          label: Text('Next 7 days${soonCount > 0 ? ' ($soonCount)' : ''}'),
          selected: _soonOnly,
          onSelected: (_) => setState(() => _soonOnly = true),
        ),
        const SizedBox(width: 8),
        ChoiceChip(
          label: const Text('All'),
          selected: !_soonOnly,
          onSelected: (_) => setState(() => _soonOnly = false),
        ),
      ]);

  /// Upcoming matches split into date sections (Today / Tomorrow / Sat 28 Jun…).
  List<Widget> _groupedUpcoming(
      BuildContext context, List<Map> upcoming, Color muted) {
    final groups = <String, List<Map>>{};
    for (final e in upcoming.take(40)) {
      (groups[e['fx']['date'] as String? ?? ''] ??= []).add(e);
    }
    final out = <Widget>[];
    for (final entry in groups.entries) {
      out.add(_sectionLabel(context, _dateLabel(entry.key), muted));
      out.addAll(entry.value.map((e) => _MatchTile(widget.data, e['key'], e['fx'])));
      out.add(const SizedBox(height: 18));
    }
    return out;
  }

  String _dateLabel(String ymd) {
    final d = DateTime.tryParse(ymd);
    if (d == null) return ymd.isEmpty ? 'Scheduled' : ymd;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final day = DateTime(d.year, d.month, d.day);
    final diff = day.difference(today).inDays;
    if (diff == 0) return 'Today';
    if (diff == 1) return 'Tomorrow';
    const wd = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const mo = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
        'Oct', 'Nov', 'Dec'];
    return '${wd[day.weekday - 1]} ${day.day} ${mo[day.month - 1]}';
  }

  /// Entry point into the "Beat the Model" game, with a live score teaser.
  Widget _beatModelCard(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return ListenableBuilder(
      listenable: beatModel,
      builder: (context, _) {
        final active = beatModel.hasActivity;
        final sub = beatModel.graded > 0
            ? 'You ${beatModel.userRight} · Model ${beatModel.modelRight} — see how you\'re doing'
            : active
                ? 'Picks locked in — awaiting results'
                : 'Predict a match. Can you out-call the algorithm?';
        return Card(
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const BeatModelScreen())),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                      color: cs.primary.withOpacity(.14),
                      borderRadius: BorderRadius.circular(12)),
                  child: Icon(Icons.sports_esports_rounded, color: cs.primary),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Beat the Model',
                          style: TextStyle(
                              fontSize: 15.5, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 2),
                      Text(sub,
                          style: TextStyle(
                              fontSize: 12.5,
                              color: cs.onSurface.withOpacity(.6))),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: cs.onSurface.withOpacity(.4)),
              ]),
            ),
          ),
        );
      },
    );
  }

  Widget _sectionLabel(BuildContext c, String t, Color color) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(t.toUpperCase(),
            style: TextStyle(
                fontSize: 11, letterSpacing: 1.3, fontWeight: FontWeight.w700, color: color)),
      );
}

/// sportKey -> (emoji, short label) for the per-tile sport badge.
const _sportBadge = {
  'clubs': ('⚽', 'Football'),
  'wc': ('🏆', 'World Cup'),
  'cl': ('⭐', 'UCL'),
  'nba': ('🏀', 'NBA'),
  'wnba': ('🏀', 'WNBA'),
  'summer': ('🏀', 'Summer Lg'),
  'nbl': ('🏀', 'NBL'),
  'ncaam': ('🏀', 'NCAA'),
  'ncaaw': ('🏀', 'NCAA W'),
  'nfl': ('🏈', 'NFL'),
};

class _MatchTile extends StatelessWidget {
  final Map data;
  final String sportKey;
  final Map f;
  const _MatchTile(this.data, this.sportKey, this.f);

  Widget _sportChip(Color accent) {
    final b = _sportBadge[sportKey] ?? ('•', sportKey.toUpperCase());
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
          color: accent.withOpacity(.15),
          borderRadius: BorderRadius.circular(6)),
      child: Text('${b.$1} ${b.$2}',
          style: TextStyle(
              fontSize: 10.5, fontWeight: FontWeight.w700, color: accent)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final accent = AppTheme.sportAccent[sportKey] ?? kBrand;
    final live = f['live'] == true;
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    // Favourite outcome text.
    String favLabel;
    double favVal;
    if (f.containsKey('home_win')) {
      final hw = (f['home_win'] as num).toDouble();
      final aw = (f['away_win'] as num).toDouble();
      favLabel = hw >= aw ? '${f['home']}' : '${f['away']}';
      favVal = hw >= aw ? hw : aw;
    } else {
      final h = (f['h'] as num).toDouble();
      final d = (f['d'] as num).toDouble();
      final a = (f['a'] as num).toDouble();
      final m = [h, d, a].reduce((x, y) => x > y ? x : y);
      favLabel = m == h ? '${f['home']}' : (m == a ? '${f['away']}' : 'Draw');
      favVal = m;
    }
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => MatchDetailScreen(
                data: data,
                sportKey: sportKey,
                home: f['home'] as String,
                away: f['away'] as String,
                fixture: f))),
        leading: DuoAvatar(f['home'] as String, f['away'] as String),
        title: Text('${f['home']}  v  ${f['away']}',
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(children: [
            _sportChip(accent),
            const SizedBox(width: 8),
            Flexible(
              child: live
                  ? Text('● LIVE${f['score'] != null ? '  ${f['score']}' : ''}',
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: Color(0xFFE5484D),
                          fontWeight: FontWeight.w700,
                          fontSize: 12))
                  : Text('${f['date']}  ·  ${f['time']}',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: muted, fontSize: 12)),
            ),
          ]),
        ),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('${(favVal * 100).round()}%',
                style: TextStyle(
                    fontWeight: FontWeight.w800, color: accent, fontSize: 16)),
            SizedBox(
                width: 96,
                child: Text(favLabel,
                    textAlign: TextAlign.right,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 11, color: muted))),
          ],
        ),
      ),
    );
  }
}
