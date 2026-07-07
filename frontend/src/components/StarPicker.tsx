import React, { useState } from 'react';
import { View, StyleSheet, PanResponder, LayoutChangeEvent, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radius, spacing } from '@/src/theme';

type Props = {
  value: number; // 0..5, 0.25 step
  onChange: (v: number) => void;
  size?: number;
  testID?: string;
};

/**
 * Tap or drag across the 5-star row to pick a rating in 0.25 increments.
 */
export function StarPicker({ value, onChange, size = 40, testID }: Props) {
  const [width, setWidth] = useState(0);
  const lastRef = React.useRef<number>(value);

  const setFromX = (x: number) => {
    if (width <= 0) return;
    const clamped = Math.max(0, Math.min(width, x));
    const raw = (clamped / width) * 5;
    const stepped = Math.round(raw * 4) / 4; // 0.25 step
    const finalV = Math.max(0.25, Math.min(5, stepped));
    if (finalV !== lastRef.current) {
      lastRef.current = finalV;
      onChange(finalV);
      Haptics.selectionAsync().catch(() => {});
    }
  };

  const panResponder = React.useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (e) => setFromX(e.nativeEvent.locationX),
        onPanResponderMove: (e) => setFromX(e.nativeEvent.locationX),
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [width],
  );

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const clamped = Math.max(0, Math.min(5, value));
  const pct = (clamped / 5) * 100;

  return (
    <View style={{ gap: spacing.sm }}>
      <View
        testID={testID}
        style={styles.wrap}
        onLayout={onLayout}
        {...panResponder.panHandlers}
      >
        <View style={styles.row}>
          {[0, 1, 2, 3, 4].map((i) => (
            <Ionicons key={i} name="star-outline" size={size} color={colors.borderStrong} />
          ))}
        </View>
        <View style={[styles.overlay, { width: `${pct}%`, pointerEvents: 'none' }]}>
          <View style={styles.row}>
            {[0, 1, 2, 3, 4].map((i) => (
              <Ionicons key={i} name="star" size={size} color={colors.brandSecondary} />
            ))}
          </View>
        </View>
      </View>
      <View style={styles.valueRow}>
        <View style={styles.valuePill}>
          <Text style={styles.valueText}>{value.toFixed(2)}</Text>
          <Text style={styles.valueSuffix}>/ 5.00</Text>
        </View>
        <Text style={styles.hint}>Drag to fine-tune (0.25 step)</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignSelf: 'flex-start', position: 'relative' },
  row: { flexDirection: 'row', gap: 4 },
  overlay: { position: 'absolute', top: 0, left: 0, height: '100%', overflow: 'hidden' },
  valueRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  valuePill: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 4,
    backgroundColor: colors.surfaceInverse,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  valueText: { color: '#fff', fontSize: 15, fontWeight: '800' },
  valueSuffix: { color: '#BBE9C9', fontSize: 12, fontWeight: '700' },
  hint: { color: colors.muted, fontSize: 12, fontStyle: 'italic' },
});
