import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'brand.dart';

/// Persists whether the user has seen the first-run onboarding.
class Onboarding {
  static const _key = 'onboarded_v1';

  static Future<bool> seen() async {
    try {
      final p = await SharedPreferences.getInstance();
      return p.getBool(_key) ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> markSeen() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(_key, true);
    } catch (_) {/* best effort */}
  }

  /// Clears the flag so the intro plays again (used by "Replay intro").
  static Future<void> reset() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.remove(_key);
    } catch (_) {/* best effort */}
  }
}

class _Page {
  final IconData icon;
  final Color accent;
  final String title;
  final String body;
  const _Page(this.icon, this.accent, this.title, this.body);
}

const _pages = <_Page>[
  _Page(
    Icons.insights_rounded,
    Color(0xFF0EA5A4),
    'Honest predictions,\nevery sport',
    'Football clubs, the World Cup, NBA, tennis and the Champions League — '
        'one clean place for grounded, data-driven forecasts.',
  ),
  _Page(
    Icons.query_stats_rounded,
    Color(0xFF2E7DF6),
    'See the reasoning,\nnot a black box',
    'Statistical models turn real results into probabilities. Every pick shows '
        'a confidence level and the “why” behind it — form, ratings, home edge.',
  ),
  _Page(
    Icons.verified_user_rounded,
    Color(0xFF16B364),
    'Straight with you,\nalways',
    'No model beats the bookmakers — if it could, we wouldn’t give it away. '
        'No sure things, no hype. Just honest odds. Please bet responsibly.',
  ),
];

/// A polished, swipeable first-run intro that leads with the honesty brand.
class OnboardingScreen extends StatefulWidget {
  final VoidCallback onDone;
  const OnboardingScreen({required this.onDone, super.key});
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _last => _page == _pages.length - 1;

  void _next() {
    if (_last) {
      widget.onDone();
    } else {
      _controller.nextPage(
          duration: const Duration(milliseconds: 420), curve: Curves.easeOutCubic);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final accent = _pages[_page].accent;
    return Scaffold(
      body: Stack(children: [
        // soft accent wash behind everything, animated per page
        AnimatedContainer(
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeOut,
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: const Alignment(0, -0.7),
              radius: 1.1,
              colors: [accent.withOpacity(.16), cs.surface.withOpacity(0)],
            ),
          ),
        ),
        SafeArea(
          child: Column(children: [
            // brand anchor + skip
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const BrandMark(compact: true),
                  AnimatedOpacity(
                    opacity: _last ? 0 : 1,
                    duration: const Duration(milliseconds: 250),
                    child: TextButton(
                      onPressed: _last ? null : widget.onDone,
                      child: Text('Skip',
                          style: TextStyle(color: cs.onSurface.withOpacity(.6))),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _controller,
                onPageChanged: (i) => setState(() => _page = i),
                itemCount: _pages.length,
                itemBuilder: (c, i) =>
                    _OnboardPageView(data: _pages[i], controller: _controller, index: i),
              ),
            ),
            // dots
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var i = 0; i < _pages.length; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeOut,
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    height: 7,
                    width: i == _page ? 22 : 7,
                    decoration: BoxDecoration(
                      color: i == _page ? accent : cs.onSurface.withOpacity(.18),
                      borderRadius: BorderRadius.circular(99),
                    ),
                  ),
              ],
            ),
            // primary action
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 22, 24, 28),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _next,
                  style: FilledButton.styleFrom(
                    backgroundColor: accent,
                    foregroundColor: Colors.white,
                    minimumSize: const Size.fromHeight(54),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(15)),
                    textStyle: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700, letterSpacing: .2),
                  ),
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 250),
                    child: Text(_last ? 'Get started' : 'Next',
                        key: ValueKey(_last)),
                  ),
                ),
              ),
            ),
          ]),
        ),
      ]),
    );
  }
}

/// One page; parallaxes + fades against the scroll position for a seamless feel.
class _OnboardPageView extends StatelessWidget {
  final _Page data;
  final PageController controller;
  final int index;
  const _OnboardPageView(
      {required this.data, required this.controller, required this.index});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final page = controller.hasClients && controller.page != null
            ? controller.page!
            : controller.initialPage.toDouble();
        final delta = page - index;
        final t = (1 - delta.abs()).clamp(0.0, 1.0);
        return Opacity(
          opacity: t,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // hero badge — extra horizontal parallax for depth
                Transform.translate(
                  offset: Offset(delta * -70, 0),
                  child: _Badge(icon: data.icon, accent: data.accent),
                ),
                const SizedBox(height: 44),
                Transform.translate(
                  offset: Offset(0, (1 - t) * 24),
                  child: Column(children: [
                    Text(
                      data.title,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 27,
                        height: 1.15,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                        color: cs.onSurface,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      data.body,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 15,
                        height: 1.5,
                        color: cs.onSurface.withOpacity(.62),
                      ),
                    ),
                  ]),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _Badge extends StatelessWidget {
  final IconData icon;
  final Color accent;
  const _Badge({required this.icon, required this.accent});

  @override
  Widget build(BuildContext context) {
    final dark = Color.lerp(accent, Colors.black, .28)!;
    return Container(
      width: 150,
      height: 150,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(42),
        gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [accent, dark]),
        boxShadow: [
          BoxShadow(
              color: accent.withOpacity(.42),
              blurRadius: 34,
              offset: const Offset(0, 16)),
        ],
      ),
      child: Icon(icon, size: 66, color: Colors.white),
    );
  }
}
