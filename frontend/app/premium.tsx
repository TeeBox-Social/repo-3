import React from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { TBButton } from '@/src/components/TBButton';

const BENEFITS: { icon: keyof typeof Ionicons.glyphMap; title: string; sub: string }[] = [
  { icon: 'remove-circle-outline', title: 'Ad-free experience', sub: 'Play and browse without interruptions.' },
  { icon: 'stats-chart-outline', title: 'Advanced stats', sub: 'Deep scoring trends, fairways, GIR & putting insights.' },
  { icon: 'heart-outline', title: 'Unlimited wishlist', sub: 'Save every course you want to play.' },
  { icon: 'ribbon-outline', title: 'Premium badge', sub: 'Stand out on your profile and in the feed.' },
];

export default function PremiumScreen() {
  useTheme();
  const router = useRouter();

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <View style={styles.header}>
        <Pressable testID="premium-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Premium</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        testID="premium-screen"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.lg }}
        showsVerticalScrollIndicator={false}
      >
        <LinearGradient
          colors={[colors.brandPrimary, colors.brandDeep]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.hero}
        >
          <View style={styles.crown}>
            <Ionicons name="star" size={28} color={colors.brandSecondary} />
          </View>
          <Text style={styles.heroTitle}>TeeBox Premium</Text>
          <Text style={styles.heroSub}>Everything you love about TeeBox — supercharged.</Text>
        </LinearGradient>

        <View style={styles.benefits}>
          {BENEFITS.map((b) => (
            <View key={b.title} style={styles.benefitRow}>
              <View style={styles.benefitIcon}>
                <Ionicons name={b.icon} size={20} color={colors.brandDeep} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.benefitTitle}>{b.title}</Text>
                <Text style={styles.benefitSub}>{b.sub}</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.priceCard}>
          <Text style={styles.priceLabel}>Planned pricing</Text>
          <Text style={styles.price}>
            $4.99<Text style={styles.priceUnit}> / month</Text>
          </Text>
          <Text style={styles.priceNote}>Final pricing & plans will be announced at launch.</Text>
        </View>

        <TBButton label="Subscribe — Coming soon" disabled onPress={() => {}} testID="premium-subscribe" />
        <Text style={styles.footnote}>
          Premium isn&apos;t available yet. Enable it here once subscriptions go live — your feedback shapes what we
          include.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  hero: { borderRadius: radius.lg, padding: spacing.xl, alignItems: 'center', gap: spacing.sm, ...shadow.card },
  crown: {
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  heroTitle: { fontSize: 24, fontWeight: '800', color: colors.onBrandPrimary },
  heroSub: { fontSize: 14, color: 'rgba(255,255,255,0.85)', textAlign: 'center' },
  benefits: { gap: spacing.md },
  benefitRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    ...shadow.card,
  },
  benefitIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  benefitTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  benefitSub: { fontSize: 12.5, color: colors.muted, marginTop: 2 },
  priceCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  priceLabel: { fontSize: 12, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 },
  price: { fontSize: 34, fontWeight: '800', color: colors.onSurface, marginTop: spacing.xs },
  priceUnit: { fontSize: 15, fontWeight: '700', color: colors.muted },
  priceNote: { fontSize: 12, color: colors.muted, marginTop: spacing.xs, textAlign: 'center' },
  footnote: { fontSize: 12, color: colors.muted, textAlign: 'center', lineHeight: 18 },
}));
