import React, { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius } from '@/src/theme';
import { api } from '@/src/api';

/**
 * Bell button with an unread badge that navigates to the Notifications screen.
 * Refreshes the unread count every time the hosting screen gains focus, so it
 * stays accurate across Feed / Discover / Log / Profile.
 */
export function NotificationBell({ color = colors.onSurface, testID }: { color?: string; testID?: string }) {
  const router = useRouter();
  const [unread, setUnread] = useState(0);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      api
        .listNotifications()
        .then((res: any) => {
          if (active) setUnread(res?.unread || 0);
        })
        .catch(() => {});
      return () => {
        active = false;
      };
    }, []),
  );

  return (
    <Pressable
      testID={testID || 'header-notifications'}
      onPress={() => router.push('/notifications')}
      style={styles.bellBtn}
      hitSlop={8}
    >
      <Ionicons name="notifications-outline" size={22} color={color} />
      {unread > 0 ? (
        <View style={styles.bellBadge}>
          <Text style={styles.bellBadgeText}>{unread > 9 ? '9+' : String(unread)}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bellBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  bellBadge: {
    position: 'absolute',
    top: 4,
    right: 4,
    minWidth: 16,
    height: 16,
    borderRadius: radius.pill,
    backgroundColor: colors.error,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  bellBadgeText: { fontSize: 10, fontWeight: '800', color: '#fff' },
});
