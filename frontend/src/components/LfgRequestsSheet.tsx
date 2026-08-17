import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { colors, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { api } from '@/src/api';

type Interest = {
  id: string;
  user_id: string;
  status: 'pending' | 'accepted' | 'declined';
  created_at: string;
  user?: { id: string; display_name: string; avatar?: string | null } | null;
};

export function LfgRequestsSheet({
  visible,
  onClose,
  roundId,
  onCountsChange,
}: {
  visible: boolean;
  onClose: () => void;
  roundId: string;
  onCountsChange?: (patch: {
    lfg_accepted_count: number;
    lfg_pending_count: number;
    lfg_spots_remaining: number | null;
  }) => void;
}) {
  const router = useRouter();
  const [items, setItems] = useState<Interest[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.lfgListInterests(roundId);
      setItems(res as any);
    } catch {
      setItems([]);
    }
  }, [roundId]);

  useEffect(() => {
    if (visible) {
      setItems(null);
      load();
    }
  }, [visible, load]);

  const respond = async (interestId: string, accept: boolean) => {
    setBusyId(interestId);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    try {
      const res = await api.lfgRespond(roundId, interestId, accept);
      setItems((prev) =>
        prev
          ? prev.map((it) => (it.id === interestId ? { ...it, status: accept ? 'accepted' : 'declined' } : it))
          : prev,
      );
      onCountsChange?.({
        lfg_accepted_count: res.lfg_accepted_count,
        lfg_pending_count: res.lfg_pending_count,
        lfg_spots_remaining: res.lfg_spots_remaining,
      });
    } catch {
      // Keep prior state — the row simply won't visually update on failure.
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet} testID="lfg-requests-sheet">
        <View style={styles.handle} />
        <View style={styles.header}>
          <Text style={styles.title}>Join requests</Text>
          <Pressable testID="lfg-requests-close" onPress={onClose} hitSlop={10}>
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>

        {items === null ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.xl }} />
        ) : items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="people-outline" size={30} color={colors.muted} />
            <Text style={styles.emptyText}>No one has asked to join yet.</Text>
          </View>
        ) : (
          <ScrollView style={{ maxHeight: 420 }} showsVerticalScrollIndicator={false}>
            {items.map((it) => {
              const name = it.user?.display_name || 'Golfer';
              const initials = name.split(' ').map((s) => s[0]).slice(0, 2).join('').toUpperCase();
              return (
                <View key={it.id} style={styles.row} testID={`lfg-request-${it.id}`}>
                  <Pressable
                    style={styles.userInfo}
                    onPress={() => {
                      if (!it.user?.id) return;
                      onClose();
                      router.push(`/user/${it.user.id}` as any);
                    }}
                  >
                    <View style={styles.avatar}>
                      {it.user?.avatar ? (
                        <Image source={{ uri: it.user.avatar }} style={{ width: '100%', height: '100%' }} />
                      ) : (
                        <Text style={styles.avatarText}>{initials}</Text>
                      )}
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={styles.name} numberOfLines={1}>{name}</Text>
                      {it.status !== 'pending' ? (
                        <Text style={[styles.statusLabel, it.status === 'accepted' ? styles.statusAccepted : styles.statusDeclined]}>
                          {it.status === 'accepted' ? 'Confirmed' : 'Declined'}
                        </Text>
                      ) : null}
                    </View>
                  </Pressable>
                  <View style={styles.actions}>
                    {busyId === it.id ? (
                      <ActivityIndicator size="small" color={colors.brandPrimary} />
                    ) : (
                      <>
                        <Pressable
                          testID={`lfg-decline-${it.id}`}
                          onPress={() => respond(it.id, false)}
                          style={[styles.actionBtn, styles.declineBtn, it.status === 'declined' && styles.declineBtnActive]}
                          hitSlop={6}
                        >
                          <Ionicons name="close" size={16} color={it.status === 'declined' ? '#fff' : '#B91C1C'} />
                        </Pressable>
                        <Pressable
                          testID={`lfg-accept-${it.id}`}
                          onPress={() => respond(it.id, true)}
                          style={[styles.actionBtn, styles.acceptBtn, it.status === 'accepted' && styles.acceptBtnActive]}
                          hitSlop={6}
                        >
                          <Ionicons name="checkmark" size={16} color={it.status === 'accepted' ? '#fff' : colors.brandPrimary} />
                        </Pressable>
                      </>
                    )}
                  </View>
                </View>
              );
            })}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.md,
    maxHeight: '75%',
  },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { fontSize: 17, fontWeight: '800', color: colors.onSurface },
  empty: { alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xl },
  emptyText: { fontSize: 13, color: colors.muted, textAlign: 'center' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
    gap: spacing.md,
  },
  userInfo: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1, minWidth: 0 },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 13 },
  name: { fontSize: 14, fontWeight: '700', color: colors.onSurface },
  statusLabel: { fontSize: 11, fontWeight: '700', marginTop: 1 },
  statusAccepted: { color: colors.success },
  statusDeclined: { color: colors.muted },
  actions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
  },
  declineBtn: { borderColor: '#F5B4B0', backgroundColor: '#FDE2E1' },
  declineBtnActive: { backgroundColor: '#DC2626', borderColor: '#DC2626' },
  acceptBtn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  acceptBtnActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
}));
