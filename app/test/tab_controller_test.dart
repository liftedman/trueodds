import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sports_model_app/markets/markets_screen.dart';

/// Regression test for the TabController ticker crash.
///
/// Both MarketsScreen and SportsScreen rebuild their TabController in
/// didUpdateWidget when the visible tab set changes — a background refresh can
/// add or drop a tab. With SingleTickerProviderStateMixin that second controller
/// needs a second ticker, which the mixin forbids:
///
///   _SportsScreenState is a SingleTickerProviderStateMixin but multiple
///   tickers were created.
///
/// The assertion leaves the TabBar holding a half-built controller, so the next
/// frame dies with "Null check operator used on a null value" and the screen is
/// unusable until restart. It shipped in both screens, so it gets a test.
///
/// This exercises MarketsScreen; SportsScreen carries the identical fix but
/// needs a full multi-sport snapshot to build its tab bodies.

Map<String, dynamic> _snapshot(List<String> assetKeys, {bool withTrack = false}) {
  const names = {
    'crypto': 'Crypto',
    'fx': 'Forex',
    'equity': 'Stocks',
    'index': 'Indices',
    'commodity': 'Commodities',
  };
  return {
    'generated': 1785970800,
    'payout': 0.80,
    'breakeven': 0.5556,
    'min_sample': 500,
    'timeframes': ['1h'],
    'asset_classes': [
      for (final k in assetKeys) {'key': k, 'name': names[k]},
    ],
    'instruments': [
      for (final k in assetKeys)
        {
          'symbol': '${k.toUpperCase()}1',
          'name': 'Test ${names[k]}',
          'asset': k,
          'last': 100.0,
          'change': 0.01,
          'change_tf': '1h',
          'spark': [98.0, 99.0, 100.0],
          'horizons': {
            '1h': {
              'p_up': 0.52,
              'ref_close': 100.0,
              // Far future so the row renders the live lean, not the
              // expired-window branch.
              'cutoff': 4102444800,
              'target': 4102448400,
              'drivers': const [],
              'track': withTrack
                  ? {
                      'n': 4000,
                      'hit': 0.521,
                      'ci': [0.505, 0.537],
                      'ev': -0.062,
                      'beats_base': true,
                      'enough': true,
                      'clears_breakeven': false,
                    }
                  : null,
            }
          },
        },
    ],
    'summary': {
      'measured': 0,
      'cleared_breakeven': 0,
      'beat_base_rate': 0,
      'mean_hit': null,
      'best_hit': null,
      'expected_false_positives': 0.0,
    },
  };
}

Widget _host(Map<String, dynamic> data) => MaterialApp(
      home: Scaffold(
        body: MarketsScreen(data, () async {}),
      ),
    );

void main() {
  testWidgets('surviving a tab being dropped does not blow the ticker',
      (tester) async {
    await tester.pumpWidget(_host(_snapshot(['crypto', 'fx', 'equity'])));
    await tester.pumpAndSettle();
    expect(find.text('₿ Crypto'), findsOneWidget);

    // A refresh drops an asset class — this is what rebuilds the controller.
    await tester.pumpWidget(_host(_snapshot(['crypto', 'fx'])));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull,
        reason: 'dropping a tab must not create a second ticker');
    expect(find.text('💱 Forex'), findsOneWidget);
  });

  testWidgets('tabs can be added and removed repeatedly', (tester) async {
    // The original bug needed only two controllers to fire. Cycling several
    // times proves the ticker is genuinely released each time rather than the
    // limit merely being higher.
    await tester.pumpWidget(_host(_snapshot(['crypto'])));
    await tester.pumpAndSettle();

    for (final keys in [
      ['crypto', 'fx'],
      ['crypto'],
      ['crypto', 'fx', 'equity', 'index'],
      ['crypto', 'fx'],
    ]) {
      await tester.pumpWidget(_host(_snapshot(keys)));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'failed on $keys');
    }
  });

  testWidgets('the selected tab is preserved when another tab disappears',
      (tester) async {
    await tester.pumpWidget(
        _host(_snapshot(['crypto', 'fx', 'equity', 'index'])));
    await tester.pumpAndSettle();

    await tester.tap(find.text('📈 Stocks')); // index 2
    await tester.pumpAndSettle();
    expect(find.text('Test Stocks'), findsOneWidget);

    // Drop the LAST class. Index 2 is still valid, so the reader should stay
    // on Stocks rather than being thrown back to the first tab.
    await tester.pumpWidget(_host(_snapshot(['crypto', 'fx', 'equity'])));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Test Stocks'), findsOneWidget);
  });

  // Overflow only shows up at real device widths, which is exactly why it
  // escaped review and turned up on the phone: a Row holding the lean chip, the
  // verdict chip and "measured X · need Y" needs ~355px and a mid-size phone
  // gives the card ~316px. Pinning several widths here catches it in CI.
  for (final width in [320.0, 360.0, 411.0]) {
    testWidgets('instrument rows do not overflow at ${width.toInt()}dp',
        (tester) async {
      tester.view.physicalSize = Size(width * 3, 800 * 3);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // withTrack: true puts the longest variant of the row on screen — the
      // one carrying the measured-vs-needed comparison.
      await tester.pumpWidget(
          _host(_snapshot(['crypto', 'fx'], withTrack: true)));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull,
          reason: 'instrument row overflowed at ${width}dp');
      expect(find.textContaining('need'), findsWidgets);
    });
  }

  testWidgets('an empty snapshot shows guidance instead of crashing',
      (tester) async {
    await tester.pumpWidget(_host(_snapshot([])));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.textContaining('No market data yet'), findsOneWidget);
  });
}
