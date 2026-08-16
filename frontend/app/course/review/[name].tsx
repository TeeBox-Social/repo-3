import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { Platform } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { StarPicker } from '@/src/components/StarPicker';

export default function PostReview() {
  useTheme();
  const { name } = useLocalSearchParams<{ name: string }>();
  const router = useRouter();
  const courseName = decodeURIComponent(String(name || ''));
  const [rating, setRating] = useState(4.0);
  const [text, setText] = useState('');
  const [posting, setPosting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    if (!text.trim()) {
      setErr('Write a quick review');
      return;
    }
    setPosting(true);
    try {
      await api.createReview({ course_name: courseName, rating, text: text.trim() });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.back();
    } catch (e: any) {
      setErr(e?.message || 'Failed to post');
    } finally {
      setPosting(false);
    }
  };

  return (
    <View style={styles.container} testID="post-review-screen">
      <SafeAreaView edges={['top']} style={styles.headerSafe}>
        <View style={styles.header}>
          <Pressable testID="review-back" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Post a review</Text>
            <Text style={styles.subtitle} numberOfLines={1}>{courseName}</Text>
          </View>
        </View>
      </SafeAreaView>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
          <Text style={styles.label}>Your rating</Text>
          <StarPicker value={rating} onChange={setRating} testID="course-star-picker" />

          <Text style={[styles.label, { marginTop: spacing.md }]}>Your review</Text>
          <TBInput
            testID="course-review-input"
            value={text}
            onChangeText={setText}
            placeholder="Fairways in great shape, greens rolled fast..."
            multiline
            style={{ minHeight: 120, textAlignVertical: 'top' }}
          />
          {err ? <Text style={styles.errText}>{err}</Text> : null}

          <TBButton
            label={posting ? 'Posting…' : 'Post review'}
            testID="course-review-submit"
            onPress={submit}
            loading={posting}
            style={{ marginTop: spacing.lg }}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  headerSafe: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  subtitle: { fontSize: 13, color: colors.muted, marginTop: 1 },
  form: { padding: spacing.xl, gap: spacing.sm, paddingBottom: 80 },
  label: { fontSize: 13, fontWeight: '700', color: colors.onSurface, letterSpacing: 0.2, marginBottom: spacing.xs },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13 },
}));
