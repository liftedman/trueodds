import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'package:sports_model_app/services/favorites.dart';

/// On-device (local) reminders — no server, no push tokens, no cost. Because the
/// app already downloads every fixture with its kickoff time, it can schedule
/// reminders itself:
///   • a heads-up ~1h before a *followed* team plays, and
///   • one "stand-out game" per day (the most coin-flippy match that day).
///
/// Everything is opt-in and capped, with quiet hours (22:00–08:00) so it never
/// wakes you at 3am. Rescheduled whenever the snapshot or your follows change.
final notifications = NotificationService();

const _leadMinutes = 60; // remind this long before kickoff
const _dailyHour = 11; // when the "game of the day" fires
const _quietStart = 22, _quietEnd = 8; // no notifications in this window
const _maxKickoff = 25, _maxDaily = 5; // safety caps

class NotificationService extends ChangeNotifier {
  final _plugin = FlutterLocalNotificationsPlugin();

  bool _enabled = false; // master switch (off until the user opts in)
  bool _kickoff = true; // remind before followed teams' games
  bool _daily = true; // the daily stand-out game
  bool _ready = false; // plugin initialised

  bool get enabled => _enabled;
  bool get kickoffOn => _kickoff;
  bool get dailyOn => _daily;

  Map? _lastData; // cached snapshot so toggles/follows can reschedule
  String _lastSig = ''; // skip rescheduling when nothing relevant changed

  /// Set up the plugin + timezone database. Does NOT ask for permission — that
  /// only happens when the user flips the master switch on.
  Future<void> init() async {
    tzdata.initializeTimeZones();
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    await _plugin.initialize(const InitializationSettings(android: android));
    final p = await SharedPreferences.getInstance();
    _enabled = p.getBool('notif_enabled') ?? false;
    _kickoff = p.getBool('notif_kickoff') ?? true;
    _daily = p.getBool('notif_daily') ?? true;
    _ready = true;
    // Following/unfollowing a team should (re)schedule its reminders at once.
    favorites.addListener(_reschedule);
  }

  Future<void> _persist() async {
    final p = await SharedPreferences.getInstance();
    await p.setBool('notif_enabled', _enabled);
    await p.setBool('notif_kickoff', _kickoff);
    await p.setBool('notif_daily', _daily);
  }

  /// Turn notifications on/off. Turning on requests OS permission first; if the
  /// user denies it, we stay off.
  Future<void> setEnabled(bool on) async {
    if (on) {
      final granted = await _requestPermission();
      if (!granted) {
        _enabled = false;
        await _persist();
        notifyListeners();
        return;
      }
    }
    _enabled = on;
    await _persist();
    notifyListeners();
    if (on) {
      _lastSig = '';
      await _reschedule();
    } else {
      await _plugin.cancelAll();
    }
  }

  Future<void> setKickoff(bool on) async {
    _kickoff = on;
    await _persist();
    notifyListeners();
    _lastSig = '';
    await _reschedule();
  }

  Future<void> setDaily(bool on) async {
    _daily = on;
    await _persist();
    notifyListeners();
    _lastSig = '';
    await _reschedule();
  }

  /// Remember that we've shown the opt-in (so we don't nag on every launch).
  Future<void> markAsked() async {
    final p = await SharedPreferences.getInstance();
    await p.setBool('notif_asked', true);
  }

  /// Ask once, ever, for users who slipped past the onboarding primer (e.g. they
  /// onboarded before notifications existed). Shows the OS prompt a single time.
  Future<void> maybeAskOnce() async {
    if (!_ready || _enabled) return;
    final p = await SharedPreferences.getInstance();
    if (p.getBool('notif_asked') ?? false) return;
    await p.setBool('notif_asked', true);
    await setEnabled(true);
  }

  Future<bool> _requestPermission() async {
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android == null) return false;
    return await android.requestNotificationsPermission() ?? false;
  }

  /// Fire a one-off notification immediately (used by the "Send a test" button).
  Future<void> sendTest() async {
    if (!_ready) return;
    await _plugin.show(999001, 'Notifications are on 🎉',
        'This is how a game reminder will look.', _details());
  }

  /// Called by the app whenever fresh snapshot data arrives. Reschedules only if
  /// the relevant fixtures/follows actually changed (so the 60s refresh is cheap).
  Future<void> sync(Map data) async {
    _lastData = data;
    await _reschedule();
  }

  Future<void> _reschedule() async {
    if (!_ready || !_enabled || _lastData == null) return;
    final games = _collect(_lastData!);
    final sig = _signature(games);
    if (sig == _lastSig) return; // nothing relevant changed
    _lastSig = sig;

    await _plugin.cancelAll();
    var id = 1;

    // 1) Kickoff reminders for followed teams.
    if (_kickoff) {
      var count = 0;
      for (final g in games) {
        if (count >= _maxKickoff) break;
        final f = g['fx'] as Map;
        if (f['live'] == true) continue;
        final home = '${f['home']}', away = '${f['away']}';
        if (!favorites.contains(home) && !favorites.contains(away)) continue;
        final ko = _kickoffTime(f);
        if (ko == null) continue;
        final when = ko.subtract(const Duration(minutes: _leadMinutes));
        if (!_schedulable(when)) continue;
        final (fav, prob) = _favourite(f);
        await _schedule(
          id++,
          '🔔 $home v $away',
          'Starts in an hour. Model leans $fav (${(prob * 100).round()}%).',
          when,
        );
        count++;
      }
    }

    // 2) One stand-out game per day (the most coin-flippy match that day).
    if (_daily) {
      final byDay = <String, List<Map>>{};
      for (final g in games) {
        final f = g['fx'] as Map;
        if (f['live'] == true) continue;
        final d = f['date'] as String?;
        if (d == null) continue;
        (byDay[d] ??= []).add(f);
      }
      final days = byDay.keys.toList()..sort();
      var count = 0;
      for (final day in days) {
        if (count >= _maxDaily) break;
        final when = _dailyTime(day);
        if (when == null || !_schedulable(when)) continue;
        // Most interesting = closest to a coin-flip.
        final pick = byDay[day]!.reduce((a, b) =>
            (_favourite(a).$2 - 0.5).abs() <= (_favourite(b).$2 - 0.5).abs()
                ? a
                : b);
        final (fav, prob) = _favourite(pick);
        final home = '${pick['home']}', away = '${pick['away']}';
        final body = prob < .55
            ? '$home v $away is essentially a coin-flip (${(prob * 100).round()}%). Anyone\'s game — a good one to fade the model.'
            : 'Today\'s stand-out: $home v $away. Model leans $fav (${(prob * 100).round()}%).';
        await _schedule(id++, '🎯 Game of the day', body, when);
        count++;
      }
    }
  }

  // ---- scheduling helpers -------------------------------------------------

  /// A future time that isn't inside quiet hours.
  bool _schedulable(DateTime when) {
    if (!when.isAfter(DateTime.now())) return false;
    final h = when.hour;
    final quiet = _quietStart > _quietEnd
        ? (h >= _quietStart || h < _quietEnd) // wraps past midnight
        : (h >= _quietStart && h < _quietEnd);
    return !quiet;
  }

  DateTime? _kickoffTime(Map f) {
    final d = f['date'] as String?;
    if (d == null) return null;
    final t = (f['time'] as String?) ?? '00:00';
    return DateTime.tryParse('${d}T${t.length >= 5 ? t.substring(0, 5) : "00:00"}:00');
  }

  DateTime? _dailyTime(String ymd) {
    final d = DateTime.tryParse(ymd);
    if (d == null) return null;
    return DateTime(d.year, d.month, d.day, _dailyHour);
  }

  Future<void> _schedule(int id, String title, String body, DateTime when) async {
    await _plugin.zonedSchedule(
      id,
      title,
      body,
      tz.TZDateTime.from(when, tz.local),
      _details(),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
    );
  }

  NotificationDetails _details() => const NotificationDetails(
        android: AndroidNotificationDetails(
          'game_reminders',
          'Game reminders',
          channelDescription:
              'Kickoff reminders for teams you follow, and the daily stand-out game.',
          importance: Importance.high,
          priority: Priority.high,
        ),
      );

  // ---- reading the snapshot ----------------------------------------------

  /// Flatten every sport's fixtures into [{key, fx}] (mirrors the Today feed).
  List<Map> _collect(Map data) {
    final out = <Map>[];
    void add(String key, List? fx) {
      for (final f in (fx ?? const [])) {
        out.add({'key': key, 'fx': f as Map});
      }
    }
    (data['leagues'] as Map?)?.forEach((_, lg) => add('clubs', lg['fixtures'] as List?));
    for (final k in ['wc', 'cl', 'nba', 'wnba', 'summer', 'nbl', 'ncaam', 'nfl']) {
      add(k, (data[k] as Map?)?['fixtures'] as List?);
    }
    return out;
  }

  /// (favourite name, its win probability) for a fixture, football or basketball.
  (String, double) _favourite(Map f) {
    if (f.containsKey('home_win')) {
      final hw = (f['home_win'] as num).toDouble();
      final aw = (f['away_win'] as num).toDouble();
      return hw >= aw ? ('${f['home']}', hw) : ('${f['away']}', aw);
    }
    final h = (f['h'] as num?)?.toDouble() ?? 0;
    final d = (f['d'] as num?)?.toDouble() ?? 0;
    final a = (f['a'] as num?)?.toDouble() ?? 0;
    final m = [h, d, a].reduce((x, y) => x > y ? x : y);
    return m == h ? ('${f['home']}', h) : (m == a ? ('${f['away']}', a) : ('Draw', d));
  }

  /// A cheap fingerprint of what we'd schedule, to avoid needless rescheduling.
  String _signature(List<Map> games) {
    final favs = (favorites.all.toList()..sort()).join(',');
    final rel = games
        .map((g) => g['fx'] as Map)
        .where((f) => f['live'] != true)
        .map((f) => '${f['home']}|${f['away']}|${f['date']}|${f['time']}')
        .toList()
      ..sort();
    return '$_enabled/$_kickoff/$_daily|$favs|${rel.join(';')}';
  }
}

/// Compact opt-in card for the About tab: master switch, the two reminder types,
/// a note on quiet hours, and a test button.
class NotificationSettingsCard extends StatelessWidget {
  const NotificationSettingsCard({super.key});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.65);
    return ListenableBuilder(
      listenable: notifications,
      builder: (context, _) {
        final on = notifications.enabled;
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('NOTIFICATIONS',
                  style: TextStyle(fontSize: 11, letterSpacing: 1.3, color: muted)),
              const SizedBox(height: 6),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Game reminders'),
                subtitle: Text(
                    'On-device only — no account, no tracking. Quiet hours 10pm–8am.',
                    style: TextStyle(fontSize: 12, color: muted)),
                value: on,
                onChanged: (v) => notifications.setEnabled(v),
              ),
              if (on) ...[
                const Divider(height: 8),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  title: const Text('Before your teams play'),
                  subtitle: Text('A heads-up ~1 hour before a followed team’s game.',
                      style: TextStyle(fontSize: 12, color: muted)),
                  value: notifications.kickoffOn,
                  onChanged: (v) => notifications.setKickoff(v),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  title: const Text('Game of the day'),
                  subtitle: Text('One stand-out match each morning.',
                      style: TextStyle(fontSize: 12, color: muted)),
                  value: notifications.dailyOn,
                  onChanged: (v) => notifications.setDaily(v),
                ),
                const SizedBox(height: 6),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () async {
                      await notifications.sendTest();
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                          content: Text('Sent a test notification.'),
                          behavior: SnackBarBehavior.floating,
                        ));
                      }
                    },
                    icon: const Icon(Icons.notifications_active_outlined, size: 18),
                    label: const Text('Send a test'),
                  ),
                ),
              ],
            ]),
          ),
        );
      },
    );
  }
}
