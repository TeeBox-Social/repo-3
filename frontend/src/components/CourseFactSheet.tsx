import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing, makeThemedSheet } from '@/src/theme';

type Tee = {
  tee_key?: string;
  tee_name?: string;
  tee_color?: string;
  gender?: string;
  course_rating?: number;
  slope?: number;
  par?: number;
  yardage?: number;
};

type Hole = {
  number: number;
  par: number;
  handicap_index?: number;
  yardages?: Record<string, number>;
};

type Climate = {
  best_months?: number[];
  monthly?: { month: number; avg_high_f?: number; avg_low_f?: number }[];
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const TEE_COLOR_HEX: Record<string, string> = {
  black: '#1A1D1C',
  blue: '#2563EB',
  gold: '#D97706',
  white: '#D1D5DB',
  green: '#15803D',
  red: '#DC2626',
  web: '#6B7161',
};

function pickHoleYardageKey(holes: Hole[]): string {
  const keys = new Set<string>();
  holes.forEach((h) => Object.keys(h.yardages || {}).forEach((k) => keys.add(k)));
  const preferred = ['white', 'blue', 'gold', 'green', 'red'];
  for (const p of preferred) if (keys.has(p)) return p;
  const rest = Array.from(keys).filter((k) => k !== 'web');
  return rest[0] || 'white';
}

export function CourseFactSheet({ info }: { info: any }) {
  const [holesTab, setHolesTab] = useState<'front' | 'back'>('front');
  const tees: Tee[] = useMemo(() => info?.tees || [], [info?.tees]);
  const holes: Hole[] = useMemo(() => info?.holes || [], [info?.holes]);
  const climate: Climate | null = info?.climate || null;

  const dedupedTees = useMemo(() => {
    // Prefer the "Male" rating card per color (common default); fall back to
    // whatever's present so unisex tee sets still render correctly.
    const byColor = new Map<string, Tee>();
    for (const t of tees) {
      const key = (t.tee_color || t.tee_name || '').toLowerCase();
      if (!key) continue;
      const existing = byColor.get(key);
      if (!existing || (t.gender || '').toLowerCase() === 'male') {
        byColor.set(key, t);
      }
    }
    return Array.from(byColor.values()).sort((a, b) => (b.yardage || 0) - (a.yardage || 0));
  }, [tees]);

  const yardageKey = useMemo(() => pickHoleYardageKey(holes), [holes]);

  const frontNine = holes.filter((h) => h.number <= 9);
  const backNine = holes.filter((h) => h.number > 9);
  const shown = holesTab === 'front' ? frontNine : backNine;
  const shownTotal = shown.reduce((sum, h) => sum + (h.par || 0), 0);
  const shownYds = shown.reduce((sum, h) => sum + ((h.yardages || {})[yardageKey] || 0), 0);

  if (!holes.length && !tees.length) return null;

  return (
    <View style={{ gap: spacing.xl }}>
      {(info?.architect || info?.year_built || info?.website || info?.phone) ? (
        <View>
          <Text style={styles.sectionTitle}>Course info</Text>
          <View style={styles.infoCard}>
            {info?.architect ? (
              <InfoRow icon="brush-outline" label="Architect" value={info.architect} />
            ) : null}
            {info?.year_built ? (
              <InfoRow icon="calendar-outline" label="Built" value={String(info.year_built)} />
            ) : null}
            {info?.website ? (
              <Pressable onPress={() => Linking.openURL(info.website).catch(() => {})}>
                <InfoRow icon="globe-outline" label="Website" value={info.website.replace(/^https?:\/\//, '')} link />
              </Pressable>
            ) : null}
            {info?.phone ? (
              <Pressable onPress={() => Linking.openURL(`tel:${info.phone}`).catch(() => {})}>
                <InfoRow icon="call-outline" label="Phone" value={info.phone} link />
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : null}

      {dedupedTees.length > 0 ? (
        <View>
          <Text style={styles.sectionTitle}>Tees</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {dedupedTees.map((t, i) => (
              <View key={`${t.tee_key || t.tee_name}-${i}`} style={styles.teeCard} testID={`course-tee-${i}`}>
                <View style={styles.teeHeaderRow}>
                  <View
                    style={[
                      styles.teeDot,
                      { backgroundColor: TEE_COLOR_HEX[(t.tee_color || '').toLowerCase()] || colors.muted },
                    ]}
                  />
                  <Text style={styles.teeName}>{t.tee_name || t.tee_color || 'Tee'}</Text>
                </View>
                <Text style={styles.teeYardage}>{t.yardage ? `${t.yardage} yds` : '—'}</Text>
                <View style={styles.teeStatsRow}>
                  {t.course_rating ? (
                    <Text style={styles.teeStat}>Rating {t.course_rating.toFixed(1)}</Text>
                  ) : null}
                  {t.slope ? <Text style={styles.teeStat}>Slope {t.slope}</Text> : null}
                </View>
              </View>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {holes.length > 0 ? (
        <View>
          <View style={styles.holesHeaderRow}>
            <Text style={styles.sectionTitle}>Hole-by-hole</Text>
            <View style={styles.holesToggle}>
              {(['front', 'back'] as const).map((k) => (
                <Pressable
                  key={k}
                  testID={`course-holes-${k}`}
                  onPress={() => setHolesTab(k)}
                  style={[styles.holesToggleBtn, holesTab === k && styles.holesToggleBtnActive]}
                >
                  <Text style={[styles.holesToggleText, holesTab === k && styles.holesToggleTextActive]}>
                    {k === 'front' ? 'Front 9' : 'Back 9'}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          <View style={styles.holesTable}>
            <View style={styles.holesRowHeader}>
              <Text style={[styles.holesCellHeader, { flex: 1.1 }]}>Hole</Text>
              <Text style={[styles.holesCellHeader, { flex: 0.8 }]}>Par</Text>
              <Text style={[styles.holesCellHeader, { flex: 0.8 }]}>HCP</Text>
              <Text style={[styles.holesCellHeader, { flex: 1.1, textAlign: 'right' }]}>Yds</Text>
            </View>
            {shown.map((h) => (
              <View key={h.number} style={styles.holesRow} testID={`course-hole-${h.number}`}>
                <Text style={[styles.holesCell, { flex: 1.1, fontWeight: '800' }]}>{h.number}</Text>
                <Text style={[styles.holesCell, { flex: 0.8 }]}>{h.par}</Text>
                <Text style={[styles.holesCell, { flex: 0.8 }]}>{h.handicap_index ?? '—'}</Text>
                <Text style={[styles.holesCell, { flex: 1.1, textAlign: 'right' }]}>
                  {(h.yardages || {})[yardageKey] ?? '—'}
                </Text>
              </View>
            ))}
            <View style={styles.holesTotalRow}>
              <Text style={[styles.holesCell, { flex: 1.1, fontWeight: '800' }]}>Total</Text>
              <Text style={[styles.holesCell, { flex: 0.8, fontWeight: '800' }]}>{shownTotal}</Text>
              <Text style={[styles.holesCell, { flex: 0.8 }]} />
              <Text style={[styles.holesCell, { flex: 1.1, textAlign: 'right', fontWeight: '800' }]}>
                {shownYds || '—'}
              </Text>
            </View>
          </View>
        </View>
      ) : null}

      {climate?.best_months?.length ? (
        <View>
          <Text style={styles.sectionTitle}>Best months to play</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {MONTHS.map((label, idx) => {
              const monthNum = idx + 1;
              const isBest = climate.best_months?.includes(monthNum);
              const stat = climate.monthly?.find((m) => m.month === monthNum);
              return (
                <View key={label} style={[styles.monthChip, isBest && styles.monthChipActive]}>
                  <Text style={[styles.monthLabel, isBest && styles.monthLabelActive]}>{label}</Text>
                  {stat?.avg_high_f != null ? (
                    <Text style={[styles.monthTemp, isBest && styles.monthLabelActive]}>{stat.avg_high_f}°</Text>
                  ) : null}
                </View>
              );
            })}
          </ScrollView>
        </View>
      ) : null}
    </View>
  );
}

function InfoRow({ icon, label, value, link }: { icon: any; label: string; value: string; link?: boolean }) {
  return (
    <View style={styles.infoRow}>
      <Ionicons name={icon} size={16} color={colors.brandPrimary} />
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={[styles.infoValue, link && styles.infoValueLink]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface, marginBottom: spacing.md },
  infoCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadow.soft,
  },
  infoRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  infoLabel: { fontSize: 12, fontWeight: '700', color: colors.muted, width: 68 },
  infoValue: { fontSize: 13, fontWeight: '700', color: colors.onSurface, flex: 1 },
  infoValueLink: { color: colors.brandPrimary, textDecorationLine: 'underline' },
  teeCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    minWidth: 118,
    gap: 4,
    ...shadow.soft,
  },
  teeHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  teeDot: { width: 12, height: 12, borderRadius: 6, borderWidth: 1, borderColor: 'rgba(0,0,0,0.15)' },
  teeName: { fontSize: 13, fontWeight: '800', color: colors.onSurface },
  teeYardage: { fontSize: 16, fontWeight: '800', color: colors.brandPrimary, marginTop: 2 },
  teeStatsRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  teeStat: { fontSize: 11, color: colors.muted, fontWeight: '600' },
  holesHeaderRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md },
  holesToggle: { flexDirection: 'row', backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, padding: 3 },
  holesToggleBtn: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  holesToggleBtnActive: { backgroundColor: colors.surfaceInverse },
  holesToggleText: { fontSize: 12, fontWeight: '800', color: colors.onSurfaceTertiary },
  holesToggleTextActive: { color: '#fff' },
  holesTable: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    overflow: 'hidden',
    ...shadow.soft,
  },
  holesRowHeader: {
    flexDirection: 'row',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surfaceTertiary,
  },
  holesCellHeader: { fontSize: 11, fontWeight: '800', color: colors.onSurfaceTertiary, letterSpacing: 0.4 },
  holesRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.md,
    paddingVertical: 9,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  holesCell: { fontSize: 13, color: colors.onSurface },
  holesTotalRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surfaceTertiary,
  },
  monthChip: {
    minWidth: 52,
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 2,
  },
  monthChipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  monthLabel: { fontSize: 12, fontWeight: '800', color: colors.onSurface },
  monthLabelActive: { color: '#fff' },
  monthTemp: { fontSize: 11, fontWeight: '600', color: colors.muted },
}));
