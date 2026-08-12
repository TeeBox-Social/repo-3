import React from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing } from '@/src/theme';

import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
type Item = {
  course_name: string;
  city?: string | null;
  region?: string | null;
  country?: string | null;
  added_at?: string;
};

type Props = {
  items: Item[];
  onRemove?: (courseName: string) => void; // if provided, show remove ×
  emptyLabel?: string;
  testID?: string;
};

export function WishlistList({ items, onRemove, emptyLabel = 'Nothing on the wishlist yet.', testID }: Props) {
  useTheme();
  const router = useRouter();
  if (!items || items.length === 0) {
    return (
      <View style={styles.emptyBox} testID={testID}>
        <Ionicons name="bookmark-outline" size={22} color={colors.muted} />
        <Text style={styles.emptyText}>{emptyLabel}</Text>
      </View>
    );
  }
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
      testID={testID}
    >
      {items.map((it) => {
        const loc = [it.city, it.region].filter(Boolean).join(', ');
        return (
          <Pressable
            key={it.course_name}
            testID={`wishlist-item-${it.course_name}`}
            onPress={() => router.push(`/course/${encodeURIComponent(it.course_name)}`)}
            style={styles.card}
          >
            <View style={styles.iconWrap}>
              <Ionicons name="bookmark" size={16} color={colors.brandDeep} />
            </View>
            <Text style={styles.name} numberOfLines={2}>
              {it.course_name}
            </Text>
            {loc ? <Text style={styles.loc} numberOfLines={1}>{loc}</Text> : null}
            {onRemove ? (
              <Pressable
                testID={`wishlist-remove-${it.course_name}`}
                hitSlop={8}
                onPress={(e) => {
                  e.stopPropagation();
                  onRemove(it.course_name);
                }}
                style={styles.removeBtn}
              >
                <Ionicons name="close" size={14} color="#fff" />
              </Pressable>
            ) : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  row: { gap: spacing.md, paddingRight: spacing.lg },
  card: {
    width: 160,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    ...shadow.soft,
    gap: 6,
    position: 'relative',
  },
  iconWrap: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: { fontSize: 13, fontWeight: '800', color: colors.onSurface, lineHeight: 17 },
  loc: { fontSize: 11, color: colors.muted, fontWeight: '600' },
  removeBtn: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 22,
    height: 22,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceInverse,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyBox: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    gap: 6,
    flexDirection: 'row',
    justifyContent: 'center',
    ...shadow.soft,
  },
  emptyText: { fontSize: 13, color: colors.muted, fontStyle: 'italic' },
}));
