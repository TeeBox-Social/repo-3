import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '@/src/theme';

type Props = {
  value: number; // 0..5, 0.25 step
  size?: number;
  color?: string;
  emptyColor?: string;
  style?: ViewStyle;
};

/**
 * Renders 5 stars with fractional fill (0.25 step) by clipping a filled star row on top of empties.
 */
export function StarDisplay({
  value,
  size = 18,
  color = colors.brandSecondary,
  emptyColor = colors.borderStrong,
  style,
}: Props) {
  const clamped = Math.max(0, Math.min(5, value));
  const pct = (clamped / 5) * 100;
  return (
    <View style={[styles.wrap, style]}>
      {/* Empty stars */}
      <View style={styles.row}>
        {[0, 1, 2, 3, 4].map((i) => (
          <Ionicons key={i} name="star-outline" size={size} color={emptyColor} />
        ))}
      </View>
      {/* Filled overlay clipped to percentage */}
      <View style={[styles.overlay, { width: `${pct}%` }]} pointerEvents="none">
        <View style={styles.row}>
          {[0, 1, 2, 3, 4].map((i) => (
            <Ionicons key={i} name="star" size={size} color={color} />
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'relative', alignSelf: 'flex-start' },
  row: { flexDirection: 'row', gap: 2 },
  overlay: { position: 'absolute', top: 0, left: 0, height: '100%', overflow: 'hidden' },
});
