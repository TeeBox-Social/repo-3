import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Switch,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api, DEFAULT_NOTIFICATION_PREFS, NotificationPrefs } from '@/src/api';
import { useAuth } from '@/src/auth-context';

type PrefRow = {
  key: keyof NotificationPrefs;
  title: string;
  desc: string;
  icon: any;
};

const ROWS: PrefRow[] = [
  {
    key: 'comment_like',
    title: 'Comment likes',
    desc: 'When someone likes a comment you made.',
    icon: 'heart-outline',
  },
  {
    key: 'achievement_unlocked',
    title: 'Achievements unlocked',
    desc: 'When you earn a new badge from a round.',
    icon: 'trophy-outline',
  },
  {
    key: 'post_like',
    title: 'Post likes',
    desc: 'When someone likes a round you posted.',
    icon: 'thumbs-up-outline',
  },
  {
    key: 'post_comment',
    title: 'New comments',
    desc: 'When someone comments on a round you posted.',
    icon: 'chatbubble-ellipses-outline',
  },
  {
    key: 'mention',
    title: '@Mentions',
    desc: 'When someone tags you in a note or comment.',
    icon: 'at-outline',
  },
  {
    key: 'follow',
    title: 'New followers',
    desc: 'When another golfer follows you.',
    icon: 'person-add-outline',
  },
  {
    key: 'course_verified',
    title: 'Course approvals',
    desc: 'When a course you submitted is approved (or rejected).',
    icon: 'checkmark-done-outline',
  },
];

export default function NotificationSettings() {
  useTheme();
  const router = useRouter();
  const { user, setUser } = useAuth();
  const [prefs, setPrefs] = useState<NotificationPrefs>(
    user?.notification_prefs || DEFAULT_NOTIFICATION_PREFS,
  );
  const [saving, setSaving] = useState<keyof NotificationPrefs | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (user?.notification_prefs) setPrefs(user.notification_prefs);
  }, [user?.notification_prefs]);

  const toggle = async (key: keyof NotificationPrefs, next: boolean) => {
    Haptics.selectionAsync().catch(() => {});
    const previous = prefs[key];
    setPrefs((p) => ({ ...p, [key]: next }));
    setSaving(key);
    setErr(null);
    try {
      const updated = await api.updateMe({
        notification_prefs: { [key]: next } as any,
      });
      setUser(updated);
      if (updated?.notification_prefs) setPrefs(updated.notification_prefs);
    } catch (e: any) {
      // Revert on failure so the toggle mirrors reality.
      setPrefs((p) => ({ ...p, [key]: previous }));
      setErr(e?.message || 'Failed to update preference');
    } finally {
      setSaving(null);
    }
  };

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <View style={styles.header}>
        <Pressable
          testID="notif-settings-back"
          onPress={() => router.back()}
          hitSlop={12}
          style={styles.backBtn}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Notifications</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        testID="notif-settings-screen"
        contentContainerStyle={{ paddingBottom: spacing.xl }}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.intro}>
          <Text style={styles.introText}>
            Choose which in-app notifications you want to receive. You can change these at
            any time.
          </Text>
        </View>

        {err ? (
          <View style={styles.errBox}>
            <Text style={styles.errText}>{err}</Text>
          </View>
        ) : null}

        <View style={styles.list}>
          {ROWS.map((r, idx) => (
            <View
              key={r.key}
              testID={`notif-pref-row-${r.key}`}
              style={[styles.row, idx === ROWS.length - 1 && styles.rowLast]}
            >
              <View style={styles.rowIcon}>
                <Ionicons name={r.icon} size={20} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{r.title}</Text>
                <Text style={styles.rowDesc}>{r.desc}</Text>
              </View>
              {saving === r.key ? (
                <ActivityIndicator color={colors.brandPrimary} size="small" />
              ) : (
                <Switch
                  testID={`notif-pref-switch-${r.key}`}
                  value={!!prefs[r.key]}
                  onValueChange={(v) => toggle(r.key, v)}
                  trackColor={{ false: colors.surfaceTertiary, true: colors.brandPrimary }}
                  thumbColor="#fff"
                />
              )}
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: colors.onSurface },
  intro: { padding: spacing.lg },
  introText: { fontSize: 14, color: colors.muted, lineHeight: 20 },
  errBox: {
    marginHorizontal: spacing.lg,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: '#FDE2E1',
    borderWidth: 1,
    borderColor: '#F5B4B0',
  },
  errText: { color: '#8B1D1A', fontSize: 13, fontWeight: '700' },
  list: {
    marginHorizontal: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    ...shadow.soft,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  rowLast: { borderBottomWidth: 0 },
  rowIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowTitle: { fontSize: 14, fontWeight: '800', color: colors.onSurface },
  rowDesc: { fontSize: 12, color: colors.muted, marginTop: 2, lineHeight: 16 },
}));
