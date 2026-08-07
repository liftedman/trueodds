import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sports_model_app/services/market_picks.dart';

/// Tests for "You vs the model".
///
/// The scoring has to be beyond doubt, because the whole value of the feature is
/// that a beginner can trust the number it gives them about themselves. If it
/// quietly flattered them it would be worse than not existing.

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('scoring', () {
    test('a DOWN call that comes off is a win', () {
      // Scoring only UP calls would flatter or punish either side depending on
      // which way the market drifted over the sample.
      final s = scorePick(userUp: false, modelPUp: 0.60, actualUp: false);
      expect(s.userRight, isTrue, reason: 'called down, went down');
      expect(s.modelRight, isFalse, reason: 'model leaned up, went down');
    });

    test('an UP call that comes off is a win', () {
      final s = scorePick(userUp: true, modelPUp: 0.40, actualUp: true);
      expect(s.userRight, isTrue);
      expect(s.modelRight, isFalse);
    });

    test('both can be right, and both can be wrong', () {
      final both = scorePick(userUp: true, modelPUp: 0.55, actualUp: true);
      expect(both.userRight, isTrue);
      expect(both.modelRight, isTrue);

      final neither = scorePick(userUp: true, modelPUp: 0.55, actualUp: false);
      expect(neither.userRight, isFalse);
      expect(neither.modelRight, isFalse);
    });

    test('p_up of exactly 0.5 counts as a DOWN lean, not a free pass', () {
      // A model with no opinion must not be scored correct by convention.
      expect(scorePick(userUp: false, modelPUp: 0.5, actualUp: false).modelRight,
          isTrue);
      expect(scorePick(userUp: true, modelPUp: 0.5, actualUp: true).modelRight,
          isFalse);
    });
  });

  group('picks store', () {
    test('a pick is recorded and retrievable by its exact bar', () async {
      final store = MarketPicksStore();
      await store.makePick(
        symbol: 'EURUSD',
        name: 'EUR/USD',
        timeframe: '1h',
        madeAtTs: 1785970800,
        settlesAt: 1785978000,
        refClose: 1.1562,
        userUp: true,
        modelPUp: 0.476,
      );

      expect(store.pending.length, 1);
      final rec = store.recordFor('EURUSD', '1h', 1785970800);
      expect(rec, isNotNull);
      expect(rec!['userUp'], isTrue);

      // A different bar of the same instrument is a different pick entirely.
      expect(store.recordFor('EURUSD', '1h', 1785974400), isNull);
      // As is a different horizon.
      expect(store.recordFor('EURUSD', '5m', 1785970800), isNull);
    });

    test('nothing is graded before it settles', () async {
      final store = MarketPicksStore();
      await store.makePick(
        symbol: 'EURUSD',
        name: 'EUR/USD',
        timeframe: '1h',
        madeAtTs: 1785970800,
        settlesAt: 1785978000,
        refClose: 1.1562,
        userUp: true,
        modelPUp: 0.476,
      );
      expect(store.graded, 0);
      expect(store.userHitRate, isNull,
          reason: 'no rate should be reported from zero settled calls');
    });

    test('picks survive a reload', () async {
      final a = MarketPicksStore();
      await a.makePick(
        symbol: 'XAUUSD',
        name: 'Gold',
        timeframe: '1h',
        madeAtTs: 111,
        settlesAt: 222,
        refClose: 4300.0,
        userUp: false,
        modelPUp: 0.51,
      );

      final b = MarketPicksStore();
      await b.load();
      final rec = b.recordFor('XAUUSD', '1h', 111);
      expect(rec, isNotNull, reason: 'a call must not vanish on restart');
      expect(rec!['userUp'], isFalse);
    });

    test('an empty store reports no rate rather than zero', () {
      final store = MarketPicksStore();
      expect(store.graded, 0);
      expect(store.userHitRate, isNull);
      expect(store.modelHitRate, isNull);
      expect(store.streak, 0);
      expect(store.hasActivity, isFalse);
    });
  });
}
