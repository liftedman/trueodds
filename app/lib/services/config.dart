/// Supabase connection for reading the prediction snapshot.
///
/// The ANON key is safe to ship in a client app (it only allows the public
/// SELECT we granted on the `snapshot` table). Paste yours below:
/// Supabase → Project Settings → API → Project URL + anon public key.
class Config {
  static const String supabaseUrl = 'https://leqydihcgjzltevgoclg.supabase.co';

  // TODO: paste your anon public key here (NOT the service_role key).
  static const String supabaseAnonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxlcXlkaWhjZ2p6bHRldmdvY2xnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODI1MDM3MTYsImV4cCI6MjA5ODA3OTcxNn0.QArdWZ7aLRJa446h8sO2iJLtAMqyd8ZgTIjfBqEUO1I';

  static String get snapshotUrl =>
      '$supabaseUrl/rest/v1/snapshot?select=data,updated_at&id=eq.latest';
}
