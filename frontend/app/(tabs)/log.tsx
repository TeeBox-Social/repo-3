import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { MentionInput } from '@/src/components/MentionInput';
import { CourseAutocomplete } from '@/src/components/CourseAutocomplete';
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
  const [postType, setPostType] = useState<'round' | 'text' | 'lfg'>('round');
  const [lookingFor, setLookingFor] = useState('');
  const [meetupDate, setMeetupDate] = useState('');  const [courseSelected, setCourseSelected] = useState(false);
  const [totalScore, setTotalScore] = useState('');
  const [par, setPar] = useState('72');
  const [holes, setHoles] = useState('18');
  const [fairways, setFairways] = useState('');
  const [gir, setGir] = useState('');
  const [putts, setPutts] = useState('');
  const [notes, setNotes] = useState('');
  const [photos, setPhotos] = useState<string[]>([]);
  const [prefillSource, setPrefillSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const applyPrefill = useCallback(() => {
    if (params.course) {
      setCourseName(String(params.course));
      // Prefill from share-intent: treat the course as selected since the source
      // app (Garmin/Grint) has already normalised the name.
      setCourseSelected(true);
    }
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
    setCourseSelected(false);
    setTotalScore('');
    setPar('72');
    setHoles('18');
    setFairways('');
    setGir('');
    setPutts('');
    setNotes('');
    setPhotos([]);
    setPrefillSource(null);
    setErr(null);
  };

  const onSubmit = async () => {
    setErr(null);
    if (postType === 'round') {
      if (!courseName.trim()) {
        setErr('Course name is required');
        return;
      }
      if (!courseSelected) {
        setErr('Please pick a course from the suggestions, or tap "Add as a new course" if it\'s missing.');
        return;
      }
      const score = Number(totalScore);
      if (!Number.isFinite(score) || score <= 0) {
        setErr('Enter a valid score');
        return;
      }
    } else {
      if (!notes.trim() && photos.length === 0) {
        setErr(postType === 'lfg' ? 'Tell others what you\u2019re looking for.' : 'Write something to share.');
        return;
      }
    }
    setLoading(true);
    try {
      const basePayload: any = {
        post_type: postType,
        notes: notes.trim(),
        photos,
      };
      if (postType === 'round') {
        basePayload.course_name = courseName.trim();
        basePayload.total_score = Number(totalScore);
        basePayload.par = Number(par) || (holes === '9' ? 36 : 72);
        basePayload.holes_played = Number(holes) || 18;
        basePayload.fairways_hit = fairways ? Number(fairways) : null;
        basePayload.greens_in_regulation = gir ? Number(gir) : null;
        basePayload.putts = putts ? Number(putts) : null;
        basePayload.hole_scores = [];
      } else if (postType === 'lfg') {
        // LFG posts no longer require a course tag — the feed presents them
        // as a stand-alone "Looking for Group" call-out.
        if (meetupDate.trim()) basePayload.meetup_date = meetupDate.trim();
        const lf = Number(lookingFor);
        if (Number.isFinite(lf) && lf > 0) basePayload.looking_for_count = lf;
      }
      await api.createRound(basePayload);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      resetForm();
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e?.message || 'Failed to save post');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container} testID="log-round-screen">
      <SafeAreaView edges={['top']} style={styles.headerSafe}>
        <View style={styles.header}>
          <Text style={styles.title}>
            {postType === 'round' ? 'Log a round' : postType === 'lfg' ? 'Looking for group' : 'New post'}
          </Text>
          <Text style={styles.subtitle}>
            {postType === 'round'
              ? 'Give the group chat something to talk about.'
              : postType === 'lfg'
                ? 'Tell your circle when you\u2019re playing and who you need.'
                : 'Share a thought, tip, or story with your circle.'}
          </Text>
          <View style={styles.segRow} testID="log-type-segment">
            {(['round', 'text', 'lfg'] as const).map((t) => (
              <Pressable
                key={t}
                testID={`log-type-${t}`}
                onPress={() => {
                  setPostType(t);
                  setErr(null);
                }}
                style={[styles.segBtn, postType === t && styles.segBtnActive]}
                hitSlop={6}
              >
                <Ionicons
                  name={t === 'round' ? 'golf' : t === 'text' ? 'chatbubble-ellipses' : 'people'}
                  size={13}
                  color={postType === t ? '#fff' : colors.onSurface}
                />
                <Text style={[styles.segText, postType === t && styles.segTextActive]}>
                  {t === 'round' ? 'Round' : t === 'text' ? 'Post' : 'LFG'}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </SafeAreaView>

      <KeyboardAwareScrollView
        contentContainerStyle={styles.form}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        bottomOffset={20}
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

          {postType === 'round' ? (
            <CourseAutocomplete
              testID="log-course"
              value={courseName}
              selected={courseSelected}
              onChangeText={(t) => {
                setCourseName(t);
                setCourseSelected(false);
              }}
              onSelect={(c) => {
                setCourseName(c.name);
                setCourseSelected(!!c.name);
                if (c.par && (!par || par === '72')) setPar(String(c.par));
              }}
            />
          ) : null}

          {postType === 'round' ? (
          <>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.dropdownLabel}>Holes</Text>
              <View style={styles.holePickerRow}>
                {(['9', '18'] as const).map((h) => {
                  const active = holes === h;
                  return (
                    <Pressable
                      key={h}
                      testID={`log-holes-${h}`}
                      onPress={() => {
                        setHoles(h);
                        // When switching hole-count, auto-flip the par default
                        // to keep it sensible (36 for 9, 72 for 18). Only do
                        // this if the user hasn't hand-typed a custom par.
                        if (h === '9' && (!par || par === '72' || par === '36')) setPar('36');
                        if (h === '18' && (!par || par === '36' || par === '72')) setPar('72');
                      }}
                      style={[styles.holePill, active && styles.holePillActive]}
                    >
                      <Text style={[styles.holePillText, active && styles.holePillTextActive]}>
                        {h}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
            <TBInput
              label="Par"
              testID="log-par"
              value={par}
              onChangeText={setPar}
              keyboardType="number-pad"
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="Total score"
              testID="log-score"
              value={totalScore}
              onChangeText={setTotalScore}
              keyboardType="number-pad"
              placeholder={holes === '9' ? '41' : '82'}
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
              placeholder={holes === '9' ? '/7' : '/14'}
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="GIR"
              testID="log-gir"
              value={gir}
              onChangeText={setGir}
              keyboardType="number-pad"
              placeholder={holes === '9' ? '/9' : '/18'}
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="Putts"
              testID="log-putts"
              value={putts}
              onChangeText={setPutts}
              keyboardType="number-pad"
              placeholder={holes === '9' ? '15' : '30'}
              containerStyle={{ flex: 1 }}
            />
          </View>
          </>
          ) : postType === 'lfg' ? (
            <View style={styles.row}>
              <TBInput
                label="Tee time / date"
                testID="log-meetup-date"
                value={meetupDate}
                onChangeText={setMeetupDate}
                placeholder="Sat 8:30 AM"
                containerStyle={{ flex: 2 }}
              />
              <TBInput
                label="Need"
                testID="log-looking-for"
                value={lookingFor}
                onChangeText={setLookingFor}
                keyboardType="number-pad"
                placeholder="2"
                containerStyle={{ flex: 1 }}
              />
            </View>
          ) : null}

          <View style={{ gap: 4 }}>
            <Text style={styles.dropdownLabel}>
              {postType === 'lfg' ? 'Details' : postType === 'text' ? 'What\u2019s on your mind?' : 'Notes'}
            </Text>
            <MentionInput
              testID="log-notes"
              value={notes}
              onChangeText={setNotes}
              multiline
              placeholder="How did it go? Type @ to tag a friend."
              style={styles.notesInput}
            />
          </View>

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
            label={
              loading
                ? 'Saving\u2026'
                : postType === 'round'
                  ? 'Save round'
                  : postType === 'lfg'
                    ? 'Post LFG'
                    : 'Post'
            }
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
      </KeyboardAwareScrollView>

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
  segRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 12,
    padding: 4,
    borderRadius: 999,
    backgroundColor: colors.surfaceTertiary,
    alignSelf: 'flex-start',
  },
  segBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
  },
  segBtnActive: { backgroundColor: colors.brandPrimary },
  segText: { fontSize: 12, fontWeight: '800', color: colors.onSurface },
  segTextActive: { color: '#fff' },
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
  holePickerRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 2,
  },
  holePill: {
    flex: 1,
    height: 46,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  holePillActive: {
    borderColor: colors.brandPrimary,
    backgroundColor: colors.brandPrimary,
  },
  holePillText: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  holePillTextActive: { color: '#fff' },
  dropdownLabel: { fontSize: 13, fontWeight: '700', color: colors.onSurface, letterSpacing: 0.2 },
  notesInput: {
    minHeight: 90,
    textAlignVertical: 'top',
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingTop: 10,
    fontSize: 15,
    color: colors.onSurface,
  },
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
