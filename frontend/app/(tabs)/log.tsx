import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Pressable,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { HoleGrid } from '@/src/components/HoleGrid';
import { api } from '@/src/api';

// This screen doubles as the Share Intent target.
// It accepts prefill params via deep link: teebox://share?course=X&score=82&par=72&notes=...
export default function LogRound() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    course?: string;
    score?: string;
    par?: string;
    holes?: string;
    fairways?: string;
    gir?: string;
    putts?: string;
    notes?: string;
    source?: string;
  }>();

  const [courseName, setCourseName] = useState('');
  const [totalScore, setTotalScore] = useState('');
  const [par, setPar] = useState('72');
  const [holes, setHoles] = useState('18');
  const [fairways, setFairways] = useState('');
  const [gir, setGir] = useState('');
  const [putts, setPutts] = useState('');
  const [notes, setNotes] = useState('');
  const [photos, setPhotos] = useState<string[]>([]);
  const [prefillSource, setPrefillSource] = useState<string | null>(null);
  const [holeScores, setHoleScores] = useState<string[]>(Array(18).fill(''));
  const [showHoles, setShowHoles] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const applyPrefill = useCallback(() => {
    if (params.course) setCourseName(String(params.course));
    if (params.score) setTotalScore(String(params.score));
    if (params.par) setPar(String(params.par));
    if (params.holes) setHoles(String(params.holes));
    if (params.fairways) setFairways(String(params.fairways));
    if (params.gir) setGir(String(params.gir));
    if (params.putts) setPutts(String(params.putts));
    if (params.notes) setNotes(String(params.notes));
    if (params.course || params.score) {
      setPrefillSource(String(params.source || 'Shared round'));
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    }
  }, [params]);

  useEffect(() => {
    applyPrefill();
  }, [applyPrefill]);

  const pickImage = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission needed', 'We need access to your photos to attach an image.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.6,
      base64: true,
      allowsEditing: true,
      aspect: [4, 3],
    });
    if (!result.canceled && result.assets[0]?.base64) {
      const uri = `data:image/jpeg;base64,${result.assets[0].base64}`;
      setPhotos((p) => [...p, uri].slice(0, 3));
      Haptics.selectionAsync().catch(() => {});
    }
  };

  const removePhoto = (idx: number) => setPhotos((p) => p.filter((_, i) => i !== idx));

  const resetForm = () => {
    setCourseName('');
    setTotalScore('');
    setPar('72');
    setHoles('18');
    setFairways('');
    setGir('');
    setPutts('');
    setNotes('');
    setPhotos([]);
    setPrefillSource(null);
    setHoleScores(Array(18).fill(''));
    setShowHoles(false);
    setErr(null);
  };

  const setHoleScore = (idx: number, v: string) => {
    setHoleScores((prev) => {
      const next = [...prev];
      next[idx] = v;
      // Auto-sum into total_score when at least one hole is filled
      const nums = next.map((s) => Number(s) || 0);
      const filled = nums.filter((n) => n > 0);
      if (filled.length > 0) {
        setTotalScore(String(nums.reduce((a, b) => a + b, 0)));
      }
      return next;
    });
  };

  const onSubmit = async () => {
    setErr(null);
    if (!courseName.trim()) {
      setErr('Course name is required');
      return;
    }
    const score = Number(totalScore);
    if (!Number.isFinite(score) || score <= 0) {
      setErr('Enter a valid score');
      return;
    }
    setLoading(true);
    try {
      const holeNums = holeScores.map((s) => Number(s) || 0);
      const hasHoles = holeNums.some((n) => n > 0);
      await api.createRound({
        course_name: courseName.trim(),
        total_score: score,
        par: Number(par) || 72,
        holes_played: Number(holes) || 18,
        fairways_hit: fairways ? Number(fairways) : null,
        greens_in_regulation: gir ? Number(gir) : null,
        putts: putts ? Number(putts) : null,
        notes: notes.trim(),
        photos,
        hole_scores: hasHoles ? holeNums : [],
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      resetForm();
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e?.message || 'Failed to save round');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container} testID="log-round-screen">
      <SafeAreaView edges={['top']} style={styles.headerSafe}>
        <View style={styles.header}>
          <Text style={styles.title}>Log a round</Text>
          <Text style={styles.subtitle}>Give the group chat something to talk about.</Text>
        </View>
      </SafeAreaView>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          contentContainerStyle={styles.form}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {prefillSource ? (
            <View testID="prefill-banner" style={styles.prefillBanner}>
              <View style={styles.prefillIcon}>
                <Ionicons name="share-social" size={16} color={colors.onBrandTertiary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.prefillTitle}>Pre-filled from {prefillSource}</Text>
                <Text style={styles.prefillSub}>Review the details and hit save.</Text>
              </View>
              <Pressable
                testID="prefill-clear"
                onPress={resetForm}
                hitSlop={8}
                style={styles.prefillClear}
              >
                <Ionicons name="close" size={16} color={colors.onSurface} />
              </Pressable>
            </View>
          ) : null}

          <TBInput
            label="Course name"
            testID="log-course"
            value={courseName}
            onChangeText={setCourseName}
            placeholder="e.g. Pebble Meadows GC"
          />

          <View style={styles.row}>
            <TBInput
              label="Total score"
              testID="log-score"
              value={totalScore}
              onChangeText={setTotalScore}
              keyboardType="number-pad"
              placeholder="82"
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="Par"
              testID="log-par"
              value={par}
              onChangeText={setPar}
              keyboardType="number-pad"
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="Holes"
              testID="log-holes"
              value={holes}
              onChangeText={setHoles}
              keyboardType="number-pad"
              containerStyle={{ flex: 1 }}
            />
          </View>

          <View style={styles.row}>
            <TBInput
              label="Fairways"
              testID="log-fairways"
              value={fairways}
              onChangeText={setFairways}
              keyboardType="number-pad"
              placeholder="/14"
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="GIR"
              testID="log-gir"
              value={gir}
              onChangeText={setGir}
              keyboardType="number-pad"
              placeholder="/18"
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="Putts"
              testID="log-putts"
              value={putts}
              onChangeText={setPutts}
              keyboardType="number-pad"
              placeholder="30"
              containerStyle={{ flex: 1 }}
            />
          </View>

          <TBInput
            label="Notes"
            testID="log-notes"
            value={notes}
            onChangeText={setNotes}
            multiline
            placeholder="How did it go? Anything memorable?"
            style={{ minHeight: 90, textAlignVertical: 'top' }}
          />

          <View style={styles.holesHeader}>
            <View style={{ flex: 1 }}>
              <Text style={styles.sectionLabel}>Hole-by-hole</Text>
              <Text style={styles.holesSub}>Optional — auto-sums into total score.</Text>
            </View>
            <Pressable
              testID="log-toggle-holes"
              onPress={() => setShowHoles((v) => !v)}
              style={styles.togglePill}
            >
              <Text style={styles.togglePillText}>{showHoles ? 'Hide' : 'Show'}</Text>
              <Ionicons
                name={showHoles ? 'chevron-up' : 'chevron-down'}
                size={14}
                color={colors.brandPrimary}
              />
            </Pressable>
          </View>
          {showHoles ? (
            <View testID="log-hole-grid">
              <HoleGrid scores={holeScores} onChangeScore={setHoleScore} />
            </View>
          ) : null}

          <Text style={styles.sectionLabel}>Photos ({photos.length}/3)</Text>
          <View style={styles.photoRow}>
            {photos.map((p, i) => (
              <Pressable
                key={i}
                testID={`log-photo-${i}`}
                onPress={() => removePhoto(i)}
                style={styles.photoThumb}
              >
                <Image source={{ uri: p }} style={styles.photoImg} contentFit="cover" />
                <View style={styles.photoRemove}>
                  <Ionicons name="close" size={14} color="#fff" />
                </View>
              </Pressable>
            ))}
            {photos.length < 3 ? (
              <Pressable testID="log-add-photo" onPress={pickImage} style={styles.photoAdd}>
                <Ionicons name="camera-outline" size={22} color={colors.brandPrimary} />
                <Text style={styles.photoAddText}>Add</Text>
              </Pressable>
            ) : null}
          </View>

          {err ? <Text style={styles.errText}>{err}</Text> : null}

          <TBButton
            label={loading ? 'Saving…' : 'Save round'}
            testID="log-submit"
            loading={loading}
            onPress={onSubmit}
            style={{ marginTop: spacing.lg }}
          />

          <View style={styles.tipBox}>
            <Ionicons name="information-circle-outline" size={16} color={colors.onSurfaceTertiary} />
            <Text style={styles.tipText}>
              Tip: In Garmin Golf or The Grint, tap Share on a round to open TeeBox pre-filled. On a
              custom EAS build, TeeBox registers a Share Extension that forwards the data to this screen.
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>

      {loading ? (
        <View style={styles.overlay}>
          <ActivityIndicator color={colors.brandPrimary} size="large" />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  headerSafe: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md },
  title: { fontSize: 26, fontWeight: '800', color: colors.onSurface },
  subtitle: { fontSize: 14, color: colors.muted, marginTop: 2 },
  form: { padding: spacing.xl, gap: spacing.md, paddingBottom: 140 },
  row: { flexDirection: 'row', gap: spacing.sm },
  sectionLabel: {
    fontSize: 13,
    fontWeight: '800',
    color: colors.onSurface,
    marginTop: spacing.sm,
    letterSpacing: 0.2,
  },
  photoRow: { flexDirection: 'row', gap: spacing.md, flexWrap: 'wrap' },
  photoThumb: {
    width: 84,
    height: 84,
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.surfaceTertiary,
  },
  photoImg: { width: '100%', height: '100%' },
  photoRemove: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 22,
    height: 22,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(19,42,28,0.85)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  photoAdd: {
    width: 84,
    height: 84,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    borderStyle: 'dashed',
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  photoAddText: { fontSize: 12, color: colors.brandPrimary, fontWeight: '700' },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13 },
  prefillBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    padding: spacing.md,
    ...shadow.soft,
  },
  prefillIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: '#B5F0C7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  prefillTitle: { fontSize: 14, fontWeight: '800', color: colors.onBrandTertiary },
  prefillSub: { fontSize: 12, color: colors.onBrandTertiary, marginTop: 2 },
  prefillClear: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  tipBox: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.surfaceTertiary,
    padding: spacing.md,
    borderRadius: radius.md,
    marginTop: spacing.lg,
  },
  tipText: { flex: 1, fontSize: 12, color: colors.onSurfaceTertiary, lineHeight: 17 },
  holesHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  holesSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  togglePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
  },
  togglePillText: { fontSize: 12, fontWeight: '800', color: colors.brandPrimary },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(253,252,248,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
