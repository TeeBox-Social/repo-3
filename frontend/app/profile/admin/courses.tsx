import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  Alert,
  RefreshControl,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { api, ImportJob } from '@/src/api';
import { useAuth } from '@/src/auth-context';

const COUNTRIES: { code: string; name: string; flag: string }[] = [
  { code: 'US', name: 'United States', flag: '🇺🇸' },
  { code: 'CA', name: 'Canada', flag: '🇨🇦' },
  { code: 'UK', name: 'United Kingdom', flag: '🇬🇧' },
  { code: 'IE', name: 'Ireland', flag: '🇮🇪' },
  { code: 'AU', name: 'Australia', flag: '🇦🇺' },
  { code: 'NZ', name: 'New Zealand', flag: '🇳🇿' },
  { code: 'JP', name: 'Japan', flag: '🇯🇵' },
  { code: 'KR', name: 'South Korea', flag: '🇰🇷' },
  { code: 'DE', name: 'Germany', flag: '🇩🇪' },
  { code: 'FR', name: 'France', flag: '🇫🇷' },
  { code: 'ES', name: 'Spain', flag: '🇪🇸' },
  { code: 'PT', name: 'Portugal', flag: '🇵🇹' },
  { code: 'IT', name: 'Italy', flag: '🇮🇹' },
  { code: 'SE', name: 'Sweden', flag: '🇸🇪' },
  { code: 'ZA', name: 'South Africa', flag: '🇿🇦' },
  { code: 'MX', name: 'Mexico', flag: '🇲🇽' },
  { code: 'AE', name: 'United Arab Emirates', flag: '🇦🇪' },
  { code: 'TH', name: 'Thailand', flag: '🇹🇭' },
];

export default function AdminCoursesScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [stats, setStats] = useState<{ total_courses: number; by_source: Record<string, number> } | null>(null);
  const [activeJob, setActiveJob] = useState<ImportJob | null>(null);
  const [recentJobs, setRecentJobs] = useState<ImportJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [s, list] = await Promise.all([api.adminCourseStats(), api.adminListJobs()]);
      setStats({ total_courses: s.total_courses, by_source: s.by_source });
      const jobs = list.jobs || [];
      const running = jobs.find((j) => j.status === 'queued' || j.status === 'running') || null;
      setActiveJob(running);
      setRecentJobs(jobs.filter((j) => j.id !== running?.id).slice(0, 8));
    } catch (e: any) {
      Alert.alert('Admin access required', e?.message || 'Only admins can view this page.');
      router.back();
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Poll active job every 3s while one is running
  useEffect(() => {
    if (!activeJob) {
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
      return;
    }
    if (pollTimer.current) return;
    pollTimer.current = setInterval(async () => {
      try {
        const fresh = await api.adminGetJob(activeJob.id);
        if (fresh.status === 'queued' || fresh.status === 'running') {
          setActiveJob(fresh);
        } else {
          setActiveJob(null);
          // Refresh stats after job finishes
          const s = await api.adminCourseStats();
          setStats({ total_courses: s.total_courses, by_source: s.by_source });
          const list = await api.adminListJobs();
          setRecentJobs((list.jobs || []).slice(0, 8));
        }
      } catch {}
    }, 3000);
    return () => {
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    };
  }, [activeJob]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadAll();
    setRefreshing(false);
  };

  const startGlobal = () => {
    Alert.alert(
      'Import all courses worldwide?',
      'This walks OpenStreetMap in 20° tiles and can take ~15–30 minutes. Overpass mirrors have rate limits so this runs slowly and safely in the background.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Start global sweep',
          style: 'default',
          onPress: async () => {
            setTriggering(true);
            try {
              await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
              const res = await api.adminImportGlobal(20, 2);
              const job = await api.adminGetJob(res.job_id);
              setActiveJob(job);
            } catch (e: any) {
              Alert.alert('Could not start job', e?.message || 'Unknown error');
            } finally {
              setTriggering(false);
            }
          },
        },
      ],
    );
  };

  const startCountry = (code: string, name: string) => {
    Alert.alert(
      `Import ${name}?`,
      'Sweeps this country only. Typically finishes in 1–5 minutes.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Import',
          style: 'default',
          onPress: async () => {
            setTriggering(true);
            try {
              await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
              const res = await api.adminImportCountry(code, 10, 2);
              const job = await api.adminGetJob(res.job_id);
              setActiveJob(job);
            } catch (e: any) {
              Alert.alert('Could not start job', e?.message || 'Unknown error');
            } finally {
              setTriggering(false);
            }
          },
        },
      ],
    );
  };

  const cancelActive = () => {
    if (!activeJob) return;
    Alert.alert('Cancel this import job?', 'Any courses already imported are kept.', [
      { text: 'Keep running', style: 'cancel' },
      {
        text: 'Cancel job',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.adminCancelJob(activeJob.id);
            await loadAll();
          } catch (e: any) {
            Alert.alert('Could not cancel', e?.message || 'Unknown error');
          }
        },
      },
    ]);
  };

  if (!user?.is_admin) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyTitle}>Admin access required</Text>
        <Text style={styles.emptySub}>Your email must be listed in ADMIN_EMAILS on the backend.</Text>
      </View>
    );
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      </View>
    );
  }

  const pct = activeJob && activeJob.total_tiles > 0
    ? Math.min(100, Math.round((activeJob.processed_tiles / activeJob.total_tiles) * 100))
    : 0;

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.backBtn}
          hitSlop={8}
          testID="admin-back"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Course Library</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 60 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Stats card */}
        <View style={styles.statsCard}>
          <Text style={styles.statsBig} testID="admin-total-courses">
            {stats?.total_courses?.toLocaleString() ?? '—'}
          </Text>
          <Text style={styles.statsLabel}>Courses in library</Text>
          <View style={styles.sourceRow}>
            {Object.entries(stats?.by_source || {}).map(([src, n]) => (
              <View key={src} style={styles.sourcePill}>
                <Text style={styles.sourceKey}>{src}</Text>
                <Text style={styles.sourceVal}>{n.toLocaleString()}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Active job */}
        {activeJob ? (
          <View style={styles.jobCard} testID="admin-active-job">
            <View style={styles.jobHeader}>
              <View style={styles.jobPulse}>
                <ActivityIndicator size="small" color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.jobTitle}>
                  {activeJob.kind === 'global' ? 'Global sweep' : `${activeJob.country} sweep`} · {activeJob.status}
                </Text>
                <Text style={styles.jobSub}>
                  {activeJob.processed_tiles} / {activeJob.total_tiles} tiles · {activeJob.inserted} new courses
                  {activeJob.errors > 0 ? ` · ${activeJob.errors} errors` : ''}
                </Text>
              </View>
            </View>
            <View style={styles.progressBar}>
              <View style={[styles.progressFill, { width: `${pct}%` }]} />
            </View>
            <Pressable onPress={cancelActive} style={styles.cancelBtn} testID="admin-cancel-job">
              <Text style={styles.cancelBtnText}>Cancel</Text>
            </Pressable>
          </View>
        ) : null}

        {/* Global action */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Bulk import</Text>
          <Text style={styles.sectionSub}>
            Sweep OpenStreetMap (free, no API key) to add golf courses in bulk. Duplicates by name are skipped.
          </Text>
          <TBButton
            label={triggering ? 'Starting…' : 'Import all courses worldwide'}
            onPress={startGlobal}
            testID="admin-global-btn"
            disabled={!!activeJob || triggering}
            style={{ marginTop: spacing.md }}
          />
          <Text style={styles.helper}>
            ≈15–30 min · 117 tiles at 20° · 2s between requests
          </Text>
        </View>

        {/* Country picker */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Import a single country</Text>
          <Text style={styles.sectionSub}>
            Faster (1–5 min per country) if you just need one region.
          </Text>
          <View style={styles.countryGrid}>
            {COUNTRIES.map((c) => (
              <Pressable
                key={c.code}
                onPress={() => startCountry(c.code, c.name)}
                disabled={!!activeJob || triggering}
                style={({ pressed }) => [
                  styles.countryChip,
                  (pressed || triggering) && { opacity: 0.7 },
                  !!activeJob && { opacity: 0.5 },
                ]}
                testID={`admin-country-${c.code}`}
              >
                <Text style={styles.countryFlag}>{c.flag}</Text>
                <Text style={styles.countryName} numberOfLines={1}>{c.name}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* Recent jobs */}
        {recentJobs.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Recent jobs</Text>
            {recentJobs.map((j) => (
              <View key={j.id} style={styles.historyRow} testID={`admin-job-${j.id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyTitle}>
                    {j.kind === 'global' ? 'Global' : (j.country || '—')} · {j.status}
                  </Text>
                  <Text style={styles.historySub}>
                    {j.inserted} new · {j.processed_tiles}/{j.total_tiles} tiles
                    {j.errors > 0 ? ` · ${j.errors} err` : ''}
                  </Text>
                </View>
                <Ionicons
                  name={
                    j.status === 'completed'
                      ? 'checkmark-circle'
                      : j.status === 'failed'
                      ? 'close-circle'
                      : j.status === 'cancelled'
                      ? 'remove-circle'
                      : 'time'
                  }
                  size={22}
                  color={
                    j.status === 'completed'
                      ? colors.brandPrimary
                      : j.status === 'failed'
                      ? '#c0392b'
                      : colors.muted
                  }
                />
              </View>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: {
    flex: 1,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '800', color: colors.onSurface, textAlign: 'center' },
  statsCard: {
    margin: spacing.lg,
    padding: spacing.xl,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.lg,
    alignItems: 'center',
    ...shadow.card,
  },
  statsBig: { fontSize: 40, fontWeight: '900', color: '#fff' },
  statsLabel: { fontSize: 13, color: 'rgba(255,255,255,0.8)', fontWeight: '600', letterSpacing: 0.5 },
  sourceRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md, flexWrap: 'wrap', justifyContent: 'center' },
  sourcePill: {
    flexDirection: 'row',
    gap: 6,
    backgroundColor: 'rgba(255,255,255,0.18)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  sourceKey: { fontSize: 11, fontWeight: '700', color: '#fff', textTransform: 'uppercase', letterSpacing: 0.4 },
  sourceVal: { fontSize: 11, fontWeight: '800', color: '#fff' },
  jobCard: {
    marginHorizontal: spacing.lg,
    padding: spacing.lg,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.lg,
    gap: spacing.md,
    ...shadow.soft,
  },
  jobHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  jobPulse: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  jobTitle: { fontSize: 15, fontWeight: '800', color: colors.onBrandTertiary },
  jobSub: { fontSize: 12, color: colors.onBrandTertiary, opacity: 0.8, marginTop: 2 },
  progressBar: {
    height: 8,
    backgroundColor: 'rgba(255,255,255,0.35)',
    borderRadius: 4,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: colors.brandPrimary },
  cancelBtn: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  cancelBtnText: { fontSize: 12, fontWeight: '800', color: colors.onSurface },
  section: { marginTop: spacing.xl, paddingHorizontal: spacing.lg },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface, marginBottom: 4 },
  sectionSub: { fontSize: 13, color: colors.muted, lineHeight: 18, marginBottom: spacing.sm },
  helper: { fontSize: 11, color: colors.muted, marginTop: spacing.sm, textAlign: 'center' },
  countryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  countryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    minWidth: 130,
    ...shadow.soft,
  },
  countryFlag: { fontSize: 18 },
  countryName: { fontSize: 13, fontWeight: '700', color: colors.onSurface, flex: 1 },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  historyTitle: { fontSize: 14, fontWeight: '700', color: colors.onSurface, textTransform: 'capitalize' },
  historySub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  emptyTitle: { fontSize: 16, fontWeight: '800', color: colors.onSurface, textAlign: 'center', marginBottom: 6 },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: 'center' },
});
