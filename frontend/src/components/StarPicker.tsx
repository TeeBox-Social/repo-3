import React, { useRef, useState } from 'react';
import { View, StyleSheet, LayoutChangeEvent, Text } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';

type Props = {
  value: number; // 0..5, 0.25 step
  onChange: (v: number) => void;
  size?: number;
  testID?: string;
};

/**
 * Tap or drag across the 5-star row to pick a rating in 0.25 increments.
 *
 * Implementation notes:
 *  - We use `react-native-gesture-handler`'s `Pan` gesture instead of the
 *    classic `PanResponder`, because `event.x` from gesture handler is
 *    always the touch coordinate in the picker's own local coordinate
 *    space on both iOS and Android — no measureInWindow / pageX / async
 *    race hazards.
 *  - The star row has NO gap between icons so the tap-position → value
 *    math is exact: each star occupies `size` px, total row width is
 *    `5 * size`. Ionicons star glyphs already have their own internal
 *    padding, so removing the flex gap doesn't make them look cramped.
 *  - Values are rounded to the nearest 0.25 and clamped to [0.25, 5.00].
 */
export function StarPicker({ value, onChange, size = 40, testID }: Props) {
  useTheme();
  const [width, setWidth] = useState(size * 5);
  const widthRef = useRef(size * 5);
  const lastRef = useRef<number>(value);

  const commit = (localX: number) => {
    const w = widthRef.current;
    if (w <= 0) return;
    const clamped = Math.max(0, Math.min(w, localX));
    const raw = (clamped / w) * 5;
    // Nearest 0.25 step, but never allow a full 0 rating — the minimum a
    // tap can produce is 0.25 so the first star always registers something.
    const stepped = Math.round(raw * 4) / 4;
    const finalV = Math.max(0.25, Math.min(5, stepped));
    if (finalV !== lastRef.current) {
      lastRef.current = finalV;
      onChange(finalV);
      Haptics.selectionAsync().catch(() => {});
    }
  };

  // Pan handles both taps (via minDistance=0 → onBegin fires immediately)
  // and drags. runOnJS keeps our commit + haptic call on the JS thread.
  const pan = Gesture.Pan()
    .minDistance(0)
    .maxPointers(1)
    .runOnJS(true)
    .onBegin((e) => commit(e.x))
    .onUpdate((e) => commit(e.x));

  // Fallback tap gesture — some Android devices with strict scroll parents
  // will cancel a Pan before it fires onBegin if the finger releases very
  // quickly. A parallel Tap catches that case.
  const tap = Gesture.Tap()
    .maxDuration(1000)
    .runOnJS(true)
    .onEnd((e, success) => {
      if (success) commit(e.x);
    });

  const gesture = Gesture.Simultaneous(pan, tap);

  const onLayout = (e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width;
    widthRef.current = w;
    setWidth(w);
  };

  const clamped = Math.max(0, Math.min(5, value));
  // Fill % is computed against the same `5 * size` total width the touch
  // math uses, so the visual fill and the numeric label are guaranteed to
  // stay in lock-step.
  const pct = (clamped / 5) * 100;

  return (
    <View style={{ gap: spacing.sm }}>
      <GestureDetector gesture={gesture}>
        <View
          testID={testID}
          style={[styles.wrap, { width: size * 5 }]}
          onLayout={onLayout}
          collapsable={false}
        >
          <View style={styles.row}>
            {[0, 1, 2, 3, 4].map((i) => (
              <View key={i} style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="star-outline" size={size} color={colors.borderStrong} />
              </View>
            ))}
          </View>
          <View style={[styles.overlay, { width: `${pct}%` }]} pointerEvents="none">
            <View style={[styles.row, { width: width || size * 5 }]}>
              {[0, 1, 2, 3, 4].map((i) => (
                <View key={i} style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="star" size={size} color={colors.brandSecondary} />
                </View>
              ))}
            </View>
          </View>
        </View>
      </GestureDetector>
      <View style={styles.valueRow}>
        <View style={styles.valuePill}>
          <Text style={styles.valueText}>{value.toFixed(2)}</Text>
          <Text style={styles.valueSuffix}>/ 5.00</Text>
        </View>
        <Text style={styles.hint}>Tap or drag (0.25 step)</Text>
      </View>
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  wrap: { alignSelf: 'flex-start', position: 'relative' },
  row: { flexDirection: 'row' },
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
}));
