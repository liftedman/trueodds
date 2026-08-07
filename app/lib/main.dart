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
import 'package:sports_model_app/markets/markets_screen.dart';
import 'package:sports_model_app/services/market_picks.dart';
import 'package:sports_model_app/services/markets_api.dart';
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
  await marketPicks.load();
  await notifications.init();
  runApp(const TrueOddsApp());
}

/// The app has two modes the user switches between. They share the shell, the
/// theme and the honesty stance, but nothing else — separate snapshots,
/// separate caches, separate failure paths.
enum AppMode { sports, markets }

class TrueOddsApp extends StatefulWidget {
  const TrueOddsApp({super.key});
  @override
  State<TrueOddsApp> createState() => _TrueOddsAppState();
}

class _TrueOddsAppState extends State<TrueOddsApp> {
  ThemeMode _mode = ThemeMode.dark;
  AppMode _app = AppMode.sports;
  int _nav = 0; // 0 Today · 1 Sports · 2 News · 3 About
  Map<String, dynamic>? _data;
  Object? _error;

  // Markets mode. Loaded lazily on first switch, so users who never open it
  // never pay for the fetch.
  Map<String, dynamic>? _markets;
  Object? _marketsError;
  bool _marketsLoading = false;
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
      if (!mounted) return;
      setState(() => _onboarded = v);
      // Returning users who onboarded before notifications existed get the
      // opt-in prompt once, on launch, instead of never being asked.
      if (v) notifications.maybeAskOnce();
    });
    Timer(const Duration(milliseconds: 2000), () {
      if (mounted) setState(() => _splash = false);
    });
    _timer =
        Timer.periodic(const Duration(seconds: 60), (_) => _refreshCurrent());
  }

  void _finishOnboarding() {
    Onboarding.markSeen();
    setState(() => _onboarded = true);
  }

  /// Android back: from a secondary tab, return to Today; from Today, require a
  /// second press within 2s before exiting (so you don't quit by accident).
  void _handleBack() {
    // Markets is a mode, not a tab — back returns to Sports rather than exiting.
    if (_app == AppMode.markets) {
      setState(() => _app = AppMode.sports);
      return;
    }
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

  // --- Markets mode --------------------------------------------------------

  /// Show any cached markets snapshot immediately, then fetch a fresh one.
  Future<void> _bootMarkets() async {
    final cache = await MarketsApi.cached();
    if (cache != null && mounted && _markets == null) {
      setState(() {
        _markets = cache['data'] as Map<String, dynamic>;
        _markets!['__updated'] = cache['updated_at'];
      });
    }
    await _loadMarkets();
  }

  Future<void> _loadMarkets() async {
    if (!mounted) return;
    setState(() => _marketsLoading = true);
    try {
      final res = await MarketsApi.fetch();
      if (!mounted) return;
      setState(() {
        _markets = res['data'] as Map<String, dynamic>;
        _markets!['__updated'] = res['updated_at'];
        _marketsError = null;
        _marketsLoading = false;
      });
      // Grade any of the user's own calls whose bar has now settled upstream.
      marketPicks.grade();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        // Keep showing cached data if we have it; only surface the error when
        // there is nothing at all to render.
        if (_markets == null) _marketsError = e;
        _marketsLoading = false;
      });
    }
  }

  void _switchMode(AppMode m) {
    setState(() => _app = m);
    if (m == AppMode.markets && _markets == null && !_marketsLoading) {
      _bootMarkets();
    }
  }

  /// The refresh button and the 60s timer act on whichever mode is on screen.
  Future<void> _refreshCurrent() =>
      _app == AppMode.markets ? _loadMarkets() : _load();

  @override
  void dispose() {
    _timer?.cancel();
    _retry?.cancel();
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
          bottom: _ModeSwitcher(mode: _app, onChanged: _switchMode),
          actions: [
            // Search covers teams and players, so it only belongs in Sports.
            if (_app == AppMode.sports && _data != null)
              Builder(
                builder: (ctx) => IconButton(
                    tooltip: 'Search',
                    icon: const Icon(Icons.search),
                    onPressed: () =>
                        showSearch(context: ctx, delegate: TeamSearch(_data!))),
              ),
            IconButton(
                tooltip: 'Refresh',
                icon: const Icon(Icons.refresh),
                onPressed: _refreshCurrent),
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
        // Markets has its own asset-class tabs; the sports nav would be
        // meaningless there, so it drops away with the mode.
        bottomNavigationBar: (!_showChrome || _app == AppMode.markets)
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

  /// App chrome shows once we're past splash + onboarding. Deliberately NOT
  /// conditional on the sports snapshot: if Sports fails to load, the mode
  /// switcher must still be reachable so Markets is not taken down with it.
  bool get _showChrome => !_splash && _onboarded == true;

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
    if (_app == AppMode.markets) return _marketsContent();

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
              SportsScreen(data, _load),
              NewsTab(data, onRefresh: _load),
              AboutTab(data, onRefresh: _load, onReplayIntro: _replayOnboarding),
            ],
          ),
        ),
      ],
    );
  }
}

/// Markets mode body: its own loading, error and content states, entirely
/// independent of the sports snapshot.
extension _MarketsBody on _TrueOddsAppState {
  Widget _marketsContent() {
    if (_markets == null && _marketsError == null) {
      return const SplashView(key: ValueKey('markets-loading'));
    }
    if (_markets == null) {
      return _ErrorView(
        key: const ValueKey('markets-error'),
        message: '$_marketsError',
        onRetry: _loadMarkets,
        hint: 'Markets data is published separately. Run '
            '`python -m markets_model.main push`.',
      );
    }
    return MarketsScreen(_markets!, _loadMarkets,
        key: const ValueKey('markets'));
  }
}

/// Slim two-way switch under the app bar. This is the top-level choice the
/// whole app hangs off, so it lives in permanent chrome rather than behind a
/// menu — you can always see which mode you are in, and leave it in one tap.
class _ModeSwitcher extends StatelessWidget implements PreferredSizeWidget {
  final AppMode mode;
  final ValueChanged<AppMode> onChanged;
  const _ModeSwitcher({required this.mode, required this.onChanged});

  @override
  Size get preferredSize => const Size.fromHeight(46);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Container(
        height: 34,
        decoration: BoxDecoration(
          color: cs.onSurface.withOpacity(.06),
          borderRadius: BorderRadius.circular(9),
        ),
        child: Row(children: [
          _seg(context, AppMode.sports, '⚽  Sports'),
          _seg(context, AppMode.markets, '📈  Markets'),
        ]),
      ),
    );
  }

  Widget _seg(BuildContext c, AppMode m, String label) {
    final cs = Theme.of(c).colorScheme;
    final on = mode == m;
    return Expanded(
      child: GestureDetector(
        onTap: () => onChanged(m),
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          margin: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            color: on ? cs.surface : null,
            borderRadius: BorderRadius.circular(7),
            boxShadow: on
                ? [BoxShadow(color: Colors.black.withOpacity(.10), blurRadius: 4)]
                : null,
          ),
          child: Center(
            child: Text(label,
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: on ? FontWeight.w700 : FontWeight.w500,
                  color: on ? cs.onSurface : cs.onSurface.withOpacity(.6),
                )),
          ),
        ),
      ),
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
  final String hint;
  const _ErrorView({
    super.key,
    required this.message,
    required this.onRetry,
    this.hint = 'Check the anon key in lib/services/config.dart, and that '
        '`python -m sports_model.main push` has run.',
  });
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
            Text(
              hint,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
