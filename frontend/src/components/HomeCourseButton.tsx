import React, { useState } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing, makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { useAuth } from '@/src/auth-context';
import { api } from '@/src/api';

type Props = {
  courseName: string;
};

/**
 * Toggleable "home course" pill for Course Detail — mirrors WishlistButton's
 * UX. Tapping sets (or clears, if already set) `home_course` on the current
 * user's profile via PATCH /auth/me, so it's reflected everywhere the
 * profile is shown (profile header, sign-up recap, etc.).
 */
export function HomeCourseButton({ courseName }: Props) {
  useTheme();
  const { user, setUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const isHome = !!user && !!user.home_course && user.home_course === courseName;

  const toggle = async () => {
    if (busy || !user) return;
    setBusy(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    try {
      const updated = await api.updateMe({ home_course: isHome ? '' : courseName });
      setUser(updated);
    } catch {
      // Swallow — button simply stays in its previous state on failure.
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;

  return (
    <Pressable
      testID="course-home-btn"
      onPress={toggle}
      style={[styles.pill, isHome ? styles.pillOn : styles.pillOff]}
      disabled={busy}
    >
      <Ionicons name={isHome ? 'home' : 'home-outline'} size={15} color={isHome ? '#fff' : colors.brandDeep} />
      <Text style={[styles.text, isHome ? styles.textOn : styles.textOff]}>
        {isHome ? 'Home course' : 'Set as home course'}
      </Text>
    </Pressable>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
    ...shadow.soft,
  },
  pillOff: { backgroundColor: '#FFFFFF' },
  pillOn: { backgroundColor: colors.brandDeep },
  text: { fontWeight: '800', fontSize: 13 },
  textOff: { color: colors.brandDeep },
  textOn: { color: '#fff' },
}));
