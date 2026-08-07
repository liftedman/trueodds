import 'package:flutter/material.dart';
import 'package:sports_model_app/predictors.dart';
import 'package:sports_model_app/widgets/brand.dart';
import 'package:sports_model_app/widgets/theme.dart';

const sportTabs = [
  ('clubs', '⚽ Clubs'),
  ('friendlies', '🤝 Friendlies'),
  ('wc', '🏆 World Cup'),
  ('basketball', '🏀 Basketball'),
  ('nfl', '🏈 NFL'),
  ('tennis', '🎾 Tennis'),
  ('cl', '⭐ UCL'),
];

/// The predictor section: sport tabs, each reskinned to its accent. A one-off
/// competition (the World Cup) drops out automatically once it has no upcoming
/// or live fixtures left, so a finished tournament stops showing.
class SportsScreen extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const SportsScreen(this.data, this.onRefresh, {super.key});
  @override
  State<SportsScreen> createState() => _SportsScreenState();
}

// TickerProviderStateMixin, not SingleTickerProviderStateMixin: didUpdateWidget
// below replaces the TabController when the visible tab set changes, and each
// controller needs its own ticker. The Single- variant permits exactly one for
// the life of the State, so the second one asserts and leaves the TabBar with a
// half-built controller ("Null check operator used on a null value").
class _SportsScreenState extends State<SportsScreen>
    with TickerProviderStateMixin {
  late List<(String, String)> _tabs;
  late TabController _controller;

  /// Whether a tab still has anything to show. Season-long tabs are always on;
  /// the World Cup and Friendlies only show while they have fixtures (a finished
  /// tournament / an empty off-season friendlies calendar drops out).
  bool _visible(String key) {
    if (key != 'wc' && key != 'friendlies') return true;
    final block = widget.data[key];
    final fx = block is Map ? block['fixtures'] as List? : null;
    return fx != null && fx.isNotEmpty;
  }

  List<(String, String)> _computeTabs() =>
      [for (final t in sportTabs) if (_visible(t.$1)) t];

  @override
  void initState() {
    super.initState();
    _tabs = _computeTabs();
    _controller = TabController(length: _tabs.length, vsync: this)
      ..addListener(_onTab);
  }

  @override
  void didUpdateWidget(SportsScreen old) {
    super.didUpdateWidget(old);
    // A refresh can add/remove a tab (e.g. the World Cup ending) — rebuild the
    // controller when the visible set changes so its length stays in sync.
    final next = _computeTabs();
    if (next.length != _tabs.length) {
      // Keep the reader where they were. Without this, a background refresh
      // that drops a tab silently throws you back to Clubs mid-scroll.
      final keep = next.isEmpty
          ? 0
          : _controller.index.clamp(0, next.length - 1);
      _controller.removeListener(_onTab);
      _controller.dispose();
      _tabs = next;
      _controller = TabController(
        length: _tabs.length,
        initialIndex: keep,
        vsync: this,
      )..addListener(_onTab);
    } else {
      _tabs = next;
    }
  }

  void _onTab() => setState(() {});

  @override
  void dispose() {
    _controller.removeListener(_onTab);
    _controller.dispose();
    super.dispose();
  }

  Widget _view(String key) {
    switch (key) {
      case 'clubs':
        return ClubsTab(widget.data, onRefresh: widget.onRefresh);
      case 'friendlies':
        return FriendliesTab(widget.data, onRefresh: widget.onRefresh);
      case 'wc':
        return EloTab(widget.data, 'wc',
            defaultNeutral: true, onRefresh: widget.onRefresh);
      case 'basketball':
        return BasketballTab(widget.data, onRefresh: widget.onRefresh);
      case 'nfl':
        return NflTab(widget.data, onRefresh: widget.onRefresh);
      case 'tennis':
        return TennisTab(widget.data, onRefresh: widget.onRefresh);
      case 'cl':
        return EloTab(widget.data, 'cl',
            defaultNeutral: false, onRefresh: widget.onRefresh);
    }
    return const SizedBox.shrink();
  }

  @override
  Widget build(BuildContext context) {
    final accent = AppTheme.sportAccent[_tabs[_controller.index].$1] ?? kBrand;
    final themed = Theme.of(context).copyWith(
      colorScheme: Theme.of(context).colorScheme.copyWith(primary: accent),
      tabBarTheme: Theme.of(context).tabBarTheme,
    );
    return Theme(
      data: themed,
      child: Column(children: [
        Material(
          color: Theme.of(context).scaffoldBackgroundColor,
          child: TabBar(
            controller: _controller,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            indicatorColor: accent,
            labelColor: accent,
            tabs: [for (final t in _tabs) Tab(text: t.$2)],
          ),
        ),
        Expanded(
          child: TabBarView(
            controller: _controller,
            children: [for (final t in _tabs) _view(t.$1)],
          ),
        ),
      ]),
    );
  }
}
