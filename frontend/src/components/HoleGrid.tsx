import React from 'react';
import { View, Text, StyleSheet, TextInput } from 'react-native';
import { colors, radius, spacing } from '@/src/theme';

import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
type Props = {
  scores: string[]; // length 18
  pars?: number[]; // length 18
  onChangeScore?: (idx: number, v: string) => void;
  readOnly?: boolean;
};

const DEFAULT_PARS = [4, 4, 3, 5, 4, 3, 4, 4, 5, 4, 3, 4, 5, 4, 4, 3, 5, 4];

export function HoleGrid({ scores, pars, onChangeScore, readOnly }: Props) {
  useTheme();
  const usedPars = pars && pars.length === 18 ? pars : DEFAULT_PARS;
  const front = Array.from({ length: 9 }, (_, i) => i);
  const back = Array.from({ length: 9 }, (_, i) => i + 9);

  const renderRow = (idxs: number[], label: string, key: string) => {
    const nine = idxs
      .map((i) => Number(scores[i]) || 0)
      .filter((n) => n > 0);
    const nineTotal = nine.reduce((a, b) => a + b, 0);
    return (
      <View style={styles.row} key={key}>
        <View style={styles.rowLabelCell}>
          <Text style={styles.rowLabel}>{label}</Text>
          <Text style={styles.rowSum}>{nineTotal || '—'}</Text>
        </View>
        {idxs.map((i) => {
          const score = Number(scores[i]) || 0;
          const diff = score ? score - usedPars[i] : null;
          const tone =
            diff == null
              ? 'neutral'
              : diff <= -2
                ? 'eagle'
                : diff === -1
                  ? 'birdie'
                  : diff === 0
                    ? 'par'
                    : diff === 1
                      ? 'bogey'
                      : 'double';
          return (
            <View key={i} style={styles.cell}>
              <Text style={styles.holeNum}>{i + 1}</Text>
              <Text style={styles.parNum}>P{usedPars[i]}</Text>
              {readOnly ? (
                <View
                  testID={`hole-${i + 1}-readonly`}
                  style={[styles.scoreDot, styles[`tone_${tone}`]]}
                >
                  <Text style={[styles.scoreText, tone !== 'neutral' && { color: '#fff' }]}>
                    {score || '—'}
                  </Text>
                </View>
              ) : (
                <TextInput
                  testID={`hole-${i + 1}-input`}
                  keyboardType="number-pad"
                  maxLength={2}
                  value={scores[i] || ''}
                  onChangeText={(t) => onChangeScore?.(i, t.replace(/[^0-9]/g, ''))}
                  style={[styles.scoreInput, styles[`tone_${tone}`], tone !== 'neutral' && { color: '#fff' }]}
                  placeholder="—"
                  placeholderTextColor={colors.muted}
                />
              )}
            </View>
          );
        })}
      </View>
    );
  };

  return (
    <View style={styles.wrap}>
      {renderRow(front, 'Front 9', 'front')}
      {renderRow(back, 'Back 9', 'back')}
      <View style={styles.legend}>
        <LegendPill color="#0E6E33" label="Birdie" />
        <LegendPill color="#4A8C57" label="Par" />
        <LegendPill color="#B84E24" label="Bogey" />
        <LegendPill color="#8A2A18" label="Double+" />
      </View>
    </View>
  );
}

function LegendPill({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendPill}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  wrap: { gap: spacing.sm },
  row: { flexDirection: 'row', gap: 4, alignItems: 'stretch' },
  rowLabelCell: {
    width: 52,
    backgroundColor: colors.surfaceInverse,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4,
  },
  rowLabel: { color: '#DCFCE7', fontSize: 10, fontWeight: '800', letterSpacing: 0.4 },
  rowSum: { color: '#fff', fontSize: 15, fontWeight: '800', marginTop: 2 },
  cell: {
    flex: 1,
    minWidth: 30,
    alignItems: 'center',
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.sm,
    paddingVertical: 4,
    gap: 2,
  },
  holeNum: { fontSize: 10, fontWeight: '800', color: colors.onSurfaceTertiary },
  parNum: { fontSize: 9, color: colors.muted, fontWeight: '700' },
  scoreInput: {
    width: '90%',
    height: 30,
    borderRadius: radius.sm,
    textAlign: 'center',
    fontSize: 14,
    fontWeight: '800',
    color: colors.onSurface,
    backgroundColor: '#fff',
  },
  scoreDot: {
    width: '90%',
    height: 30,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  scoreText: { fontSize: 14, fontWeight: '800', color: colors.onSurface },
  tone_neutral: {},
  tone_par: { backgroundColor: '#4A8C57' },
  tone_birdie: { backgroundColor: '#0E6E33' },
  tone_eagle: { backgroundColor: '#0B4A22' },
  tone_bogey: { backgroundColor: '#B84E24' },
  tone_double: { backgroundColor: '#8A2A18' },
  legend: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap', marginTop: spacing.xs },
  legendPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.surfaceTertiary,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  legendDot: { width: 10, height: 10, borderRadius: radius.pill },
  legendText: { fontSize: 11, color: colors.onSurfaceTertiary, fontWeight: '700' },
}));
