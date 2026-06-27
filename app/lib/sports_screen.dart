import 'package:flutter/material.dart';
import 'brand.dart';
import 'predictors.dart';
import 'theme.dart';

const sportTabs = [
  ('clubs', '⚽ Clubs'),
  ('wc', '🏆 World Cup'),
  ('nba', '🏀 NBA'),
  ('tennis', '🎾 Tennis'),
  ('cl', '⭐ UCL'),
];

/// The predictor section: 5 sport tabs, each reskinned to its accent.
class SportsScreen extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  final TabController controller;
  const SportsScreen(this.data, this.controller, this.onRefresh, {super.key});
  @override
  State<SportsScreen> createState() => _SportsScreenState();
}

class _SportsScreenState extends State<SportsScreen> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onTab);
  }

  void _onTab() => setState(() {});

  @override
  void dispose() {
    widget.controller.removeListener(_onTab);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final accent =
        AppTheme.sportAccent[sportTabs[widget.controller.index].$1] ?? kBrand;
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
            controller: widget.controller,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            indicatorColor: accent,
            labelColor: accent,
            tabs: [for (final t in sportTabs) Tab(text: t.$2)],
          ),
        ),
        Expanded(
          child: TabBarView(
            controller: widget.controller,
            children: [
              ClubsTab(widget.data, onRefresh: widget.onRefresh),
              EloTab(widget.data, 'wc', defaultNeutral: true, onRefresh: widget.onRefresh),
              NbaTab(widget.data, onRefresh: widget.onRefresh),
              TennisTab(widget.data, onRefresh: widget.onRefresh),
              EloTab(widget.data, 'cl', defaultNeutral: false, onRefresh: widget.onRefresh),
            ],
          ),
        ),
      ]),
    );
  }
}
