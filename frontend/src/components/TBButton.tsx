import React from 'react';
import { Pressable, StyleSheet, Text, ActivityIndicator, ViewStyle, TextStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import { colors, radius, spacing, shadow } from '@/src/theme';

type Props = {
  label: string;
  onPress?: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'ghost';
  style?: ViewStyle;
  labelStyle?: TextStyle;
  testID?: string;
  icon?: React.ReactNode;
};

export function TBButton({
  label,
  onPress,
  loading,
  disabled,
  variant = 'primary',
  style,
  labelStyle,
  testID,
  icon,
}: Props) {
  const isDisabled = disabled || loading;
  const bg =
    variant === 'primary'
      ? colors.brandPrimary
      : variant === 'secondary'
        ? colors.surfaceSecondary
        : 'transparent';
  const fg =
    variant === 'primary'
      ? colors.onBrandPrimary
      : variant === 'secondary'
        ? colors.onSurfaceSecondary
        : colors.brandPrimary;
  const border =
    variant === 'secondary' ? { borderWidth: 1.5, borderColor: colors.borderStrong } : {};

  return (
    <Pressable
      testID={testID}
      onPress={() => {
        if (isDisabled) return;
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
        onPress?.();
      }}
      style={({ pressed }) => [
        styles.base,
        variant === 'primary' && shadow.card,
        { backgroundColor: bg, opacity: isDisabled ? 0.55 : pressed ? 0.9 : 1 },
        border,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon}
          <Text style={[styles.label, { color: fg }, labelStyle]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 54,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
  },
  label: {
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
});
