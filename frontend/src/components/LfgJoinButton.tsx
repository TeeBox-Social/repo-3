import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth-context';

/** Shared "Need X more" / "Group is full" label for LFG banners. */
export function lfgSpotsLabel(round: any): string | null {
  if (round?.lfg_spots_remaining != null) {
    return round.lfg_spots_remaining === 0 ? 'Group is full' : `Need ${round.lfg_spots_remaining} more`;
  }
  if (round?.looking_for_count) return `Need ${round.looking_for_count} more`;
  return null;
}

type LfgPatch = {
  lfg_my_interest: { id: string; status: 'pending' } | null;
  lfg_accepted_count: number;
  lfg_pending_count: number;
  lfg_spots_remaining: number | null;
};

export function LfgJoinButton({
  round,
  onUpdate,
  compact,
}: {
  round: any;
  onUpdate?: (patch: LfgPatch) => void;
  compact?: boolean;
}) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user || round.user_id === user.id) return null; // organizers manage requests instead

  const myStatus: 'pending' | 'accepted' | 'declined' | null = round.lfg_my_interest?.status || null;
  const spotsRemaining = round.lfg_spots_remaining;
  const isFull = round.looking_for_count != null && spotsRemaining === 0 && myStatus !== 'accepted' && myStatus !== 'pending';

  const onPress = async () => {
    if (loading || myStatus === 'accepted' || isFull) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setLoading(true);
    setError(null);
    try {
      const res = await api.lfgToggleInterest(round.id);
      onUpdate?.({
        lfg_my_interest: res.status ? { id: res.interest_id as string, status: 'pending' } : null,
        lfg_accepted_count: res.lfg_accepted_count,
        lfg_pending_count: res.lfg_pending_count,
        lfg_spots_remaining: res.lfg_spots_remaining,
      });
    } catch (e: any) {
      setError(e?.message || 'Please try again.');
    } finally {
      setLoading(false);
    }
  };

  let label = "I'm in!";
  let icon: any = 'hand-right-outline';
  let variant = styles.btnPrimary;
  let textVariant = styles.btnText;
  let iconColor = '#fff';

  if (myStatus === 'accepted') {
    label = "You're confirmed";
    icon = 'checkmark-circle';
    variant = styles.btnConfirmed;
  } else if (myStatus === 'pending') {
    label = 'Requested';
    icon = 'time-outline';
    variant = styles.btnPending;
    textVariant = styles.btnTextPending;
    iconColor = '#7A4E00';
  } else if (isFull) {
    label = 'Full';
    icon = 'lock-closed-outline';
    variant = styles.btnFull;
    textVariant = styles.btnTextFull;
    iconColor = colors.muted;
  }

  const disabled = loading || myStatus === 'accepted' || isFull;

  return (
    <>
      <Pressable
        testID={`lfg-join-${round.id}`}
        onPress={onPress}
        disabled={disabled}
        style={[styles.btn, variant, compact && styles.btnCompact, disabled && !loading && myStatus !== 'accepted' && { opacity: isFull ? 0.7 : 1 }]}
      >
        {loading ? (
          <ActivityIndicator size="small" color={iconColor} />
        ) : (
          <>
            <Ionicons name={icon} size={16} color={iconColor} />
            <Text style={textVariant}>{label}</Text>
          </>
        )}
      </Pressable>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    borderRadius: radius.pill,
    alignSelf: 'stretch',
  },
  btnCompact: { paddingVertical: 10, alignSelf: 'flex-start', paddingHorizontal: spacing.lg },
  btnPrimary: { backgroundColor: colors.brandPrimary },
  btnConfirmed: { backgroundColor: colors.success ?? '#1E8E3E' },
  btnPending: { backgroundColor: '#FFF4D6', borderWidth: 1, borderColor: '#F0DBA0' },
  btnFull: { backgroundColor: colors.surfaceTertiary },
  btnText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  btnTextPending: { color: '#7A4E00', fontWeight: '800', fontSize: 14 },
  btnTextFull: { color: colors.muted, fontWeight: '800', fontSize: 14 },
  errorText: { color: colors.error ?? '#B91C1C', fontSize: 12, fontWeight: '600', marginTop: 4 },
}));
