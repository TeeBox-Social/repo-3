import React from 'react';
import { StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';
import { colors, radius, spacing } from '@/src/theme';

import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
type Props = TextInputProps & {
  label?: string;
  error?: string;
  containerStyle?: any;
  rightAdornment?: React.ReactNode;
};

export function TBInput({ label, error, containerStyle, rightAdornment, style, ...rest }: Props) {
  useTheme();
  return (
    <View style={[styles.wrap, containerStyle]}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View style={[styles.inputBox, error ? styles.errorBorder : null]}>
        <TextInput
          placeholderTextColor={colors.muted}
          style={[styles.input, style]}
          {...rest}
        />
        {rightAdornment}
      </View>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  wrap: { width: '100%' },
  label: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.onSurface,
    marginBottom: spacing.xs,
    letterSpacing: 0.2,
  },
  inputBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    minHeight: 54,
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: colors.onSurface,
    paddingVertical: spacing.md,
  },
  errorBorder: { borderColor: colors.error },
  errorText: { color: colors.error, marginTop: 4, fontSize: 12, fontWeight: '600' },
}));
