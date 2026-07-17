import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sports_model_app/screens/about.dart';
import 'package:sports_model_app/services/api.dart';
import 'package:sports_model_app/services/beat_model.dart';
import 'package:sports_model_app/widgets/brand.dart';
import 'package:sports_model_app/services/crests.dart';
import 'package:sports_model_app/services/favorites.dart';
import 'package:sports_model_app/screens/home_screen.dart';
import 'package:sports_model_app/services/notifications.dart';
import 'package:sports_model_app/screens/news.dart';
import 'package:sports_model_app/screens/onboarding.dart';
import 'package:sports_model_app/screens/search.dart';
import 'package:sports_model_app/screens/sports_screen.dart';
import 'package:sports_model_app/widgets/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await favorites.load();
  await beatModel.load();
  await notifications.init();
  runApp(const TrueOddsApp());
}

class TrueOddsApp extends StatefulWidget {
  const TrueOddsApp({super.key});
  @override
  State<TrueOddsApp> createState() => _TrueOddsAppState();
}

class _TrueOddsAppState extends State<TrueOddsApp> with TickerProviderStateMixin {
  late final TabController _sportsTab =
      TabController(length: sportTabs.length, vsync: this);
  ThemeMode _mode = ThemeMode.dark;
  int _nav = 0; // 0 Today · 1 Sports · 2 News · 3 About
  Map<String, dynamic>? _data;
  Object? _error;
  bool _stale = false; // showing cached data; last fetch did not succeed
  bool _splash = true; // keep the brand on screen briefly on every launch
  bool? _onboarded; // null = still checking the first-run flag
  DateTime? _lastBack; // for "press back again to exit"
  Timer? _timer; // normal 60s refresh
  Timer? _retry; // fast retry while offline, cancels itself once back online

  @override
  void initState() {
    super.initState();
    _boot();
    Onboarding.seen().then((v) {
      if (mounted) setState(() => _onboarded = v);
    });
    Timer(const Duration(milliseconds: 2000), () {
      if (mounted) setState(() => _splash = false);
    });
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => _load());
  }

  void _finishOnboarding() {
    Onboarding.markSeen();
    setState(() => _onboarded = true);
  }

  /// Android back: from a secondary tab, return to Today; from Today, require a
  /// second press within 2s before exiting (so you don't quit by accident).
  void _handleBack() {
    if (_nav != 0) {
      setState(() => _nav = 0);
      return;
    }
    final now = DateTime.now();
    if (_lastBack == null || now.difference(_lastBack!) > const Duration(seconds: 2)) {
      _lastBack = now;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Press back again to exit'),
        duration: Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
      ));
      return;
    }
    SystemNavigator.pop(); // second press within the window — leave the app
  }

  void _replayOnboarding() {
    Onboarding.reset();
    setState(() {
      _onboarded = false;
      _nav = 0;
    });
  }

  /// Show the cached snapshot immediately (instant cold start), then refresh.
  Future<void> _boot() async {
    final cache = await SnapshotApi.cached();
    if (cache != null && mounted && _data == null) {
      setState(() {
        _data = cache['data'] as Map<String, dynamic>;
        _data!['__updated'] = cache['updated_at'];
        _stale = true; // provisional until a live fetch confirms
      });
      loadTeamCrests(_data!);
      beatModel.grade(_data!['results'] as List?);
      notifications.sync(_data!);
    }
    await _load();
  }

  Future<void> _load() async {
    try {
      final res = await SnapshotApi.fetch();
      if (!mounted) return;
      _retry?.cancel(); // back online — stop the fast retry loop
      _retry = null;
      setState(() {
        _data = res['data'] as Map<String, dynamic>;
        _data!['__updated'] = res['updated_at'];
        _error = null;
        _stale = false;
      });
      loadTeamCrests(_data!);
      beatModel.grade(_data!['results'] as List?); // grade picks vs results
      notifications.sync(_data!); // (re)schedule reminders if enabled
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (_data != null) {
          _stale = true; // keep last good data on screen
        } else {
          _error = e;
        }
      });
      _scheduleRetry();
    }
  }

  /// While offline, poll every 12s so the app refreshes itself the moment the
  /// connection returns — no pull-to-refresh needed.
  void _scheduleRetry() {
    _retry ??= Timer.periodic(const Duration(seconds: 12), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _retry?.cancel();
    _sportsTab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TrueOdds',
      debugShowCheckedModeBanner: false,
      themeMode: _mode,
      theme: AppTheme.light(kBrand),
      darkTheme: AppTheme.dark(kBrand),
      home: PopScope(
        canPop: false, // we handle back ourselves (tab-aware + exit guard)
        onPopInvokedWithResult: (didPop, result) {
          if (!didPop) _handleBack();
        },
        child: Scaffold(
          appBar: _showChrome
            ? AppBar(
          titleSpacing: 16,
          title: const BrandMark(compact: true),
          actions: [
            Builder(
              builder: (ctx) => IconButton(
                  tooltip: 'Search',
                  icon: const Icon(Icons.search),
                  onPressed: () =>
                      showSearch(context: ctx, delegate: TeamSearch(_data!))),
            ),
            IconButton(
                tooltip: 'Refresh', icon: const Icon(Icons.refresh), onPressed: _load),
            IconButton(
              tooltip: 'Light / dark',
              icon: Icon(_mode == ThemeMode.dark
                  ? Icons.light_mode_outlined
                  : Icons.dark_mode_outlined),
              onPressed: () => setState(() => _mode =
                  _mode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark),
            ),
          ],
        )
            : null,
        body: _body(),
        bottomNavigationBar: !_showChrome
            ? null
            : NavigationBar(
                selectedIndex: _nav,
                onDestinationSelected: (i) => setState(() => _nav = i),
                destinations: const [
                  NavigationDestination(
                      icon: Icon(Icons.today_outlined),
                      selectedIcon: Icon(Icons.today),
                      label: 'Today'),
                  NavigationDestination(
                      icon: Icon(Icons.sports_soccer_outlined),
                      selectedIcon: Icon(Icons.sports_soccer),
                      label: 'Sports'),
                  NavigationDestination(
                      icon: Icon(Icons.newspaper_outlined),
                      selectedIcon: Icon(Icons.newspaper),
                      label: 'News'),
                  NavigationDestination(
                      icon: Icon(Icons.info_outline),
                      selectedIcon: Icon(Icons.info),
                      label: 'About'),
                ],
              ),
        ),
      ),
    );
  }

  /// App chrome (bars) only show once we're past splash + onboarding with data.
  bool get _showChrome =>
      !_splash && _onboarded == true && _data != null;

  Widget _body() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      child: _content(),
    );
  }

  Widget _content() {
    // Splash until the timer elapses AND the first-run flag is known.
    if (_splash || _onboarded == null) {
      return const SplashView(key: ValueKey('splash'));
    }
    if (_onboarded == false) {
      return OnboardingScreen(
          key: const ValueKey('onboard'), onDone: _finishOnboarding);
    }
    if (_data == null && _error == null) {
      return const SplashView(key: ValueKey('loading'));
    }
    if (_data == null) {
      return _ErrorView(
          key: const ValueKey('error'), message: '$_error', onRetry: _load);
    }
    final data = _data!;
    return Column(
      key: const ValueKey('content'),
      children: [
        if (_stale) _StaleBanner(updated: data['__updated'] as String?),
        Expanded(
          child: IndexedStack(
            index: _nav,
            children: [
              TodayScreen(data, _load),
              SportsScreen(data, _sportsTab, _load),
              NewsTab(data, onRefresh: _load),
              AboutTab(data, onRefresh: _load, onReplayIntro: _replayOnboarding),
            ],
          ),
        ),
      ],
    );
  }
}

/// A thin strip shown when the live feed is unreachable and we're displaying
/// the last cached snapshot.
class _StaleBanner extends StatelessWidget {
  final String? updated;
  const _StaleBanner({this.updated});

  String _ago() {
    if (updated == null) return '';
    final t = DateTime.tryParse(updated!);
    if (t == null) return '';
    final d = DateTime.now().toUtc().difference(t.toUtc());
    if (d.inMinutes < 1) return ' · just now';
    if (d.inHours < 1) return ' · ${d.inMinutes}m ago';
    if (d.inDays < 1) return ' · ${d.inHours}h ago';
    return ' · ${d.inDays}d ago';
  }

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme;
    return Material(
      color: c.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
        child: Row(children: [
          Icon(Icons.cloud_off_outlined, size: 15, color: c.onSurface.withOpacity(.7)),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Offline — showing last update${_ago()}',
                style: TextStyle(fontSize: 12, color: c.onSurface.withOpacity(.7))),
          ),
        ]),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const _ErrorView({super.key, required this.message, required this.onRetry});
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.cloud_off, size: 40),
            const SizedBox(height: 12),
            const Text('Could not load predictions',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
            const SizedBox(height: 16),
            const Text(
              'Check the anon key in lib/config.dart, and that '
              '`python -m sports_model.main push` has run.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
