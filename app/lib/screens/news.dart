import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:sports_model_app/widgets/theme.dart';

Color _accentFor(String sport) =>
    AppTheme.sportAccent[sport == 'football' ? 'clubs' : sport] ??
    const Color(0xFF0EA5A4);

String _ago(String? iso) {
  if (iso == null) return '';
  final t = DateTime.tryParse(iso);
  if (t == null) return '';
  final d = DateTime.now().toUtc().difference(t.toUtc());
  if (d.inMinutes < 1) return 'just now';
  if (d.inMinutes < 60) return '${d.inMinutes}m ago';
  if (d.inHours < 24) return '${d.inHours}h ago';
  return '${d.inDays}d ago';
}

Future<void> _openExternal(BuildContext context, String? url) async {
  final uri = url == null ? null : Uri.tryParse(url);
  if (uri == null) return;
  final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
  if (!ok && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the article.')));
  }
}

/// Sport news feed — reputable headlines, newest first, tap for a clean reader.
class NewsTab extends StatefulWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const NewsTab(this.data, {required this.onRefresh, super.key});
  @override
  State<NewsTab> createState() => _NewsTabState();
}

class _NewsTabState extends State<NewsTab> {
  String _filter = 'all';

  static const _filters = [
    ('all', 'All'),
    ('football', 'Football'),
    ('nba', 'NBA'),
    ('tennis', 'Tennis'),
    ('general', 'General'),
  ];

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    final all = ((widget.data['news'] as List?) ?? const []).cast<Map>().toList();
    final items = _filter == 'all'
        ? all
        : all.where((e) => e['sport'] == _filter).toList();

    return RefreshIndicator(
      onRefresh: widget.onRefresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          const Text('News',
              style: TextStyle(
                  fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -.5)),
          Text('Latest from across the sporting world',
              style: TextStyle(color: muted)),
          const SizedBox(height: 14),
          SizedBox(
            height: 38,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (final f in _filters)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(f.$2),
                      selected: _filter == f.$1,
                      onSelected: (_) => setState(() => _filter = f.$1),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          if (all.isEmpty)
            _empty(context, muted, 'No news right now',
                'The feed refreshes when the engine next publishes. Pull down to retry.')
          else if (items.isEmpty)
            _empty(context, muted, 'Nothing here yet',
                'No recent stories in this category. Try another filter.')
          else
            ...items.map((e) => _NewsCard(e)),
        ],
      ),
    );
  }

  Widget _empty(BuildContext c, Color muted, String title, String body) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 48),
        child: Column(children: [
          Icon(Icons.newspaper_outlined, size: 40, color: muted),
          const SizedBox(height: 12),
          Text(title,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          const SizedBox(height: 6),
          Text(body, textAlign: TextAlign.center, style: TextStyle(color: muted)),
        ]),
      );
}

/// A thumbnail that fades in and quietly disappears if the image fails.
class _Thumb extends StatelessWidget {
  final String? url;
  final double? width, height;
  final BorderRadius radius;
  const _Thumb(this.url, {this.width, this.height, required this.radius});

  @override
  Widget build(BuildContext context) {
    if (url == null || url!.isEmpty) return const SizedBox.shrink();
    return ClipRRect(
      borderRadius: radius,
      child: Image.network(
        url!,
        width: width,
        height: height,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => const SizedBox.shrink(),
        loadingBuilder: (c, child, progress) {
          if (progress == null) return child;
          return Container(
            width: width,
            height: height,
            color: Theme.of(c).colorScheme.surfaceContainerHighest,
          );
        },
      ),
    );
  }
}

class _NewsCard extends StatelessWidget {
  final Map item;
  const _NewsCard(this.item);

  @override
  Widget build(BuildContext context) {
    final accent = _accentFor(item['sport'] as String? ?? '');
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    final image = item['image'] as String?;
    final hasImage = image != null && image.isNotEmpty;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => NewsDetailScreen(item))),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (hasImage)
              _Thumb(image,
                  height: 168,
                  width: double.infinity,
                  radius: BorderRadius.zero),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    _SourceChip(item['source'] as String? ?? '', accent),
                    const Spacer(),
                    Text(_ago(item['published'] as String?),
                        style: TextStyle(fontSize: 11, color: muted)),
                  ]),
                  const SizedBox(height: 8),
                  Text(item['title'] as String? ?? '',
                      style: const TextStyle(
                          fontSize: 15.5,
                          fontWeight: FontWeight.w700,
                          height: 1.25)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SourceChip extends StatelessWidget {
  final String source;
  final Color accent;
  const _SourceChip(this.source, this.accent);
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
            color: accent.withOpacity(.14),
            borderRadius: BorderRadius.circular(6)),
        child: Text(source,
            style: TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, color: accent)),
      );
}

/// A clean in-app reader: hero image, headline, summary, and a link out.
class NewsDetailScreen extends StatelessWidget {
  final Map item;
  const NewsDetailScreen(this.item, {super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final accent = _accentFor(item['sport'] as String? ?? '');
    final image = item['image'] as String?;
    final summary = (item['summary'] as String?) ?? '';

    return Scaffold(
      appBar: AppBar(title: Text(item['source'] as String? ?? 'Article')),
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          if (image != null && image.isNotEmpty)
            _Thumb(image,
                width: double.infinity, height: 230, radius: BorderRadius.zero),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  _SourceChip(item['source'] as String? ?? '', accent),
                  const SizedBox(width: 10),
                  Text(_ago(item['published'] as String?),
                      style: TextStyle(fontSize: 12, color: muted)),
                ]),
                const SizedBox(height: 16),
                Text(item['title'] as String? ?? '',
                    style: const TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        height: 1.25,
                        letterSpacing: -0.4)),
                const SizedBox(height: 18),
                if (summary.isNotEmpty)
                  Text(summary,
                      style: TextStyle(
                          fontSize: 16, height: 1.6, color: cs.onSurface.withOpacity(.85))),
                const SizedBox(height: 28),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () => _openExternal(context, item['url'] as String?),
                    style: FilledButton.styleFrom(
                      backgroundColor: accent,
                      foregroundColor: Colors.white,
                      minimumSize: const Size.fromHeight(52),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    icon: const Icon(Icons.open_in_new_rounded, size: 18),
                    label: const Text('Read full article',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  ),
                ),
                const SizedBox(height: 12),
                Center(
                  child: Text('Opens ${item['source'] ?? 'the source'} in your browser',
                      style: TextStyle(fontSize: 12, color: muted)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
