import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, spacing } from '@/src/theme';

type LikersSource =
  | { kind: 'round'; roundId: string }
  | { kind: 'comment'; roundId: string; commentId: string };

type Props = {
  visible: boolean;
  onClose: () => void;
  source: LikersSource | null;
  title?: string;
  /** Injected loaders so this component stays decoupled from the api module. */
  fetchRoundLikers: (roundId: string) => Promise<any[]>;
  fetchCommentLikers: (roundId: string, commentId: string) => Promise<any[]>;
};

/**
 * Bottom sheet listing the users who liked a round or a comment.
 * Tapping a user navigates to their profile.
 */
export function LikersSheet({
  visible,
  onClose,
  source,
  title = 'Liked by',
  fetchRoundLikers,
  fetchCommentLikers,
}: Props) {
  const router = useRouter();
  const [users, setUsers] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!source) return;
    setLoading(true);
    setUsers(null);
    try {
      const list =
        source.kind === 'round'
          ? await fetchRoundLikers(source.roundId)
          : await fetchCommentLikers(source.roundId, source.commentId);
      setUsers(list || []);
    } catch {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [source, fetchRoundLikers, fetchCommentLikers]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const openUser = (id?: string) => {
    if (!id) return;
    onClose();
    router.push(`/user/${id}` as any);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet} testID="likers-sheet">
        <View style={styles.handle} />
        <View style={styles.header}>
          <Text style={styles.title}>{title}</Text>
          <Pressable testID="likers-close" onPress={onClose} hitSlop={10}>
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>

        {loading ? (
          <View style={styles.centerPad}>
            <ActivityIndicator color={colors.brandPrimary} />
          </View>
        ) : users && users.length > 0 ? (
          <FlatList
            data={users}
            keyExtractor={(u) => u.id}
            contentContainerStyle={styles.listContent}
            renderItem={({ item }) => <LikerRow user={item} onPress={() => openUser(item.id)} />}
            showsVerticalScrollIndicator={false}
          />
        ) : (
          <View style={styles.centerPad}>
            <Ionicons name="heart-outline" size={30} color={colors.muted} />
            <Text style={styles.emptyText}>No likes yet</Text>
          </View>
        )}
      </View>
    </Modal>
  );
}

function LikerRow({ user, onPress }: { user: any; onPress: () => void }) {
  const initials = (user.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <Pressable testID={`liker-${user.id}`} onPress={onPress} style={styles.row}>
      <View style={styles.avatar}>
        {user.avatar ? (
          <Image source={{ uri: user.avatar }} style={{ width: '100%', height: '100%' }} />
        ) : (
          <Text style={styles.avatarText}>{initials}</Text>
        )}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.name} numberOfLines={1}>{user.display_name || 'Golfer'}</Text>
        <Text style={styles.sub} numberOfLines={1}>
          {user.home_course ? `${user.home_course} · ` : ''}
          {user.handicap != null ? `HC ${user.handicap}` : 'Golfer'}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '70%',
    minHeight: 220,
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xl,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  title: { fontSize: 17, fontWeight: '800', color: colors.onSurface },
  centerPad: { paddingVertical: 48, alignItems: 'center', gap: spacing.sm },
  emptyText: { fontSize: 14, color: colors.muted, fontWeight: '600' },
  listContent: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 15 },
  name: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  sub: { fontSize: 13, color: colors.muted, marginTop: 2 },
});
