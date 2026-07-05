import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';

type Props = {
  courseName: string;
  onChange?: (added: boolean) => void;
};

/** Toggleable wishlist pill for Course Detail. */
export function WishlistButton({ courseName, onChange }: Props) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'busy'>('loading');
  const [on, setOn] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await api.checkWishlist(courseName);
        if (alive) setOn(res.on_wishlist);
      } catch {}
      if (alive) setStatus('idle');
    })();
    return () => {
      alive = false;
    };
  }, [courseName]);

  const toggle = async () => {
    if (status !== 'idle') return;
    setStatus('busy');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    const next = !on;
    setOn(next);
    try {
      if (next) await api.addWishlist(courseName);
      else await api.removeWishlist(courseName);
      onChange?.(next);
    } catch {
      setOn(!next); // revert
    } finally {
      setStatus('idle');
    }
  };

  return (
    <Pressable
      testID="course-wishlist-btn"
      onPress={toggle}
      style={[styles.pill, on ? styles.pillOn : styles.pillOff]}
      disabled={status !== 'idle'}
    >
      {status === 'loading' ? (
        <ActivityIndicator size="small" color={colors.brandDeep} />
      ) : (
        <>
          <Ionicons
            name={on ? 'bookmark' : 'bookmark-outline'}
            size={15}
            color={on ? '#fff' : colors.brandDeep}
          />
          <Text style={[styles.text, on ? styles.textOn : styles.textOff]}>
            {on ? 'On wishlist' : 'Add to wishlist'}
          </Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
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
});
