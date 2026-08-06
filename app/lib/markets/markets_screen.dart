import 'package:flutter/material.dart';
import 'package:sports_model_app/markets/instrument_detail.dart';
import 'package:sports_model_app/markets/market_widgets.dart';
import 'package:sports_model_app/widgets/brand.dart';
import 'package:sports_model_app/widgets/live_prob.dart' show Sparkline;
import 'package:sports_model_app/widgets/theme.dart';

/// Markets mode: one tab per asset class, mirroring SportsScreen's structure.
///
/// A tab only appears if the snapshot actually carries instruments for it, the
/// same way the World Cup tab drops out when it has no fixtures left. That
/// keeps the app honest about coverage instead of showing empty promises.
class MarketsScreen extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const MarketsScreen(this.data, this.onRefresh, {super.key});

  @override
  State<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketsScreenState extends State<MarketsScreen>
    with SingleTickerProviderStateMixin {
  late List<Map> _classes;
  late TabController _controller;

  /// Shared across tabs — switching asset class shouldn't reset the horizon
  /// you're studying.
  late String _tf;

  List<Map> _computeClasses() =>
      ((widget.data['asset_classes'] as List?) ?? const []).cast<Map>();

  List<String> get _timeframes =>
      [for (final t in (widget.data['timeframes'] as List? ?? const [])) t as String];

  @override
  void initState() {
    super.initState();
    _classes = _computeClasses();
    final tfs = _timeframes;
    // Default to 1h: long enough to have a solid measured sample everywhere,
    // short enough to be the horizon people actually trade.
    _tf = tfs.contains('1h') ? '1h' : (tfs.isNotEmpty ? tfs.last : '1h');
    _controller = TabController(length: _classes.length, vsync: this)
      ..addListener(_onTab);
  }

  @override
  void didUpdateWidget(MarketsScreen old) {
    super.didUpdateWidget(old);
    final next = _computeClasses();
    if (next.length != _classes.length) {
      _controller.removeListener(_onTab);
      _controller.dispose();
      _classes = next;
      _controller = TabController(length: _classes.length, vsync: this)
        ..addListener(_onTab);
    } else {
      _classes = next;
    }
  }

  void _onTab() => setState(() {});

  @override
  void dispose() {
    _controller.removeListener(_onTab);
    _controller.dispose();
    super.dispose();
  }

  List _instrumentsFor(String assetKey) =>
      ((widget.data['instruments'] as List?) ?? const [])
          .where((i) => (i as Map)['asset'] == assetKey)
          .toList();

  @override
  Widget build(BuildContext context) {
    if (_classes.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Text(
            'No market data yet.\n\nRun:  python -m markets_model.main ingest\n'
            'then: python -m markets_model.main push',
            textAlign: TextAlign.center,
            style: TextStyle(
                color: Theme.of(context).colorScheme.onSurface.withOpacity(.6)),
          ),
        ),
      );
    }

    final key = _classes[_controller.index]['key'] as String;
    final accent = AppTheme.sportAccent[key] ?? kBrand;
    final themed = Theme.of(context).copyWith(
      colorScheme: Theme.of(context).colorScheme.copyWith(primary: accent),
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
            tabs: [
              for (final c in _classes)
                Tab(text: '${_assetIcon(c['key'] as String)} ${c['name']}')
            ],
          ),
        ),
        _horizonBar(context, accent),
        Expanded(
          child: TabBarView(
            controller: _controller,
            children: [
              for (final c in _classes)
                _InstrumentList(
                  data: widget.data,
                  instruments: _instrumentsFor(c['key'] as String),
                  timeframe: _tf,
                  accent: AppTheme.sportAccent[c['key'] as String] ?? kBrand,
                  onRefresh: widget.onRefresh,
                )
            ],
          ),
        ),
      ]),
    );
  }

  /// Horizon picker plus the standing breakeven reminder. Putting the breakeven
  /// in the persistent chrome — not buried in a detail page — means a user can
  /// never scan a list of confident-looking percentages without the bar they
  /// have to clear being on screen at the same time.
  Widget _horizonBar(BuildContext c, Color accent) {
    final cs = Theme.of(c).colorScheme;
    final breakeven = (widget.data['breakeven'] as num).toDouble();
    final payout = (widget.data['payout'] as num).toDouble();
    final tfs = _timeframes;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
      decoration: BoxDecoration(
        color: Theme.of(c).scaffoldBackgroundColor,
        border: Border(bottom: BorderSide(color: Theme.of(c).dividerColor)),
      ),
      child: Column(children: [
        Row(children: [
          Text('HORIZON',
              style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.2,
                  color: cs.onSurface.withOpacity(.6))),
          const SizedBox(width: 10),
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: [
                for (final t in tfs) ...[
                  _tfChip(c, t, accent),
                  const SizedBox(width: 6),
                ]
              ]),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Icon(Icons.info_outline, size: 13, color: cs.onSurface.withOpacity(.55)),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
                'At a ${(payout * 100).round()}% fixed payout you need '
                '${pctM(breakeven)} accuracy just to break even.',
                style: TextStyle(
                    fontSize: 11.5, color: cs.onSurface.withOpacity(.7))),
          ),
        ]),
      ]),
    );
  }

  Widget _tfChip(BuildContext c, String t, Color accent) {
    final on = t == _tf;
    return InkWell(
      onTap: () => setState(() => _tf = t),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
        decoration: BoxDecoration(
          color: on ? accent.withOpacity(.14) : null,
          border: Border.all(
              color: on
                  ? accent
                  : Theme.of(c).colorScheme.onSurface.withOpacity(.18)),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(t,
            style: TextStyle(
                fontSize: 12,
                fontWeight: on ? FontWeight.w700 : FontWeight.w500,
                color: on ? accent : null)),
      ),
    );
  }
}

String _assetIcon(String key) => switch (key) {
      'crypto' => '₿',
      'fx' => '💱',
      'equity' => '📈',
      'index' => '🏛',
      'commodity' => '🛢',
      _ => '•',
    };

/// The scrollable list of instruments for one asset class.
class _InstrumentList extends StatelessWidget {
  final Map data;
  final List instruments;
  final String timeframe;
  final Color accent;
  final Future<void> Function() onRefresh;
  const _InstrumentList({
    required this.data,
    required this.instruments,
    required this.timeframe,
    required this.accent,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    final breakeven = (data['breakeven'] as num).toDouble();

    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
        children: [
          MarketsSummaryCard(data),
          const SizedBox(height: 12),
          if (data['live_record'] != null) ...[
            LiveRecordCard(data),
            const SizedBox(height: 12),
          ],
          if (instruments.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 40),
              child: Text('Nothing ingested for this asset class yet.',
                  textAlign: TextAlign.center, style: TextStyle(color: muted)),
            )
          else
            Card(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                child: Column(children: [
                  for (var i = 0; i < instruments.length; i++) ...[
                    _row(context, instruments[i] as Map, breakeven, muted),
                    if (i < instruments.length - 1)
                      Divider(
                          height: 1, color: Theme.of(context).dividerColor),
                  ]
                ]),
              ),
            ),
          const MarketsDisclosure(),
        ],
      ),
    );
  }

  Widget _row(BuildContext c, Map inst, double breakeven, Color muted) {
    final horizons = inst['horizons'] as Map;
    final h = horizons[timeframe] as Map?;
    final change = (inst['change'] as num).toDouble();
    final spark = [for (final v in inst['spark'] as List) (v as num).toDouble()];

    final pUp = h == null ? null : (h['p_up'] as num).toDouble();
    final side = pUp == null ? '' : (pUp >= .5 ? 'UP' : 'DOWN');
    final pSide = pUp == null ? null : (pUp >= .5 ? pUp : 1 - pUp);
    final (vLabel, vColor, _) = marketVerdict(h?['track'] as Map?, breakeven);

    return InkWell(
      onTap: () => Navigator.of(c).push(MaterialPageRoute(
          builder: (_) => InstrumentDetail(data, inst, timeframe))),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Column(children: [
          Row(children: [
            Expanded(
              flex: 4,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${inst['name']}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 14.5)),
                Text('${inst['symbol']}',
                    style: TextStyle(fontSize: 10.5, color: muted)),
              ]),
            ),
            if (spark.length > 2)
              Expanded(
                flex: 3,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Sparkline(spark, changeColor(c, change), height: 26),
                ),
              ),
            Expanded(
              flex: 3,
              child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text(priceStr(inst['last'] as num?),
                    style: const TextStyle(
                        fontSize: 13.5,
                        fontWeight: FontWeight.w700,
                        fontFeatures: [FontFeature.tabularFigures()])),
                Text(
                    '${change >= 0 ? '+' : ''}${(change * 100).toStringAsFixed(2)}%',
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: changeColor(c, change))),
              ]),
            ),
            Icon(Icons.chevron_right, size: 18, color: muted),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            if (pSide == null)
              Text('No model at $timeframe',
                  style: TextStyle(fontSize: 11.5, color: muted))
            else if (isExpired(h!)) ...[
              // The window closed before this snapshot reached the device, so
              // there is no live call to show — only the record.
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  border: Border.all(color: muted.withOpacity(.35)),
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.history_toggle_off, size: 11, color: muted),
                  const SizedBox(width: 4),
                  Text('closed ${expiredAgo(h)}',
                      style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w600,
                          color: muted)),
                ]),
              ),
              const SizedBox(width: 6),
              VerdictChip(vLabel, vColor, dense: true),
            ] else ...[
              // The lean is shown deliberately muted, never as a call to act.
              // The verdict chip beside it carries the weight.
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  border: Border.all(color: muted.withOpacity(.4)),
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Text('leans $side ${pctM(pSide)}',
                    style: TextStyle(
                        fontSize: 10.5,
                        fontWeight: FontWeight.w600,
                        color: Theme.of(c).colorScheme.onSurface.withOpacity(.75))),
              ),
              const SizedBox(width: 6),
              VerdictChip(vLabel, vColor, dense: true),
            ],
            const Spacer(),
            if (h?['track'] != null && (h!['track'] as Map)['enough'] == true)
              Text(
                  'measured ${pctM(((h['track'] as Map)['hit'] as num).toDouble())}'
                  ' · need ${pctM(breakeven)}',
                  style: TextStyle(fontSize: 10.5, color: muted)),
          ]),
        ]),
      ),
    );
  }
}
