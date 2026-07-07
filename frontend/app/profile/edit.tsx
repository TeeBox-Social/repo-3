import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth-context';

export default function ProfileEdit() {
  const router = useRouter();
  const { user, setUser } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [handicap, setHandicap] = useState(user?.handicap != null ? String(user.handicap) : '');
  const [homeCourse, setHomeCourse] = useState(user?.home_course || '');
  const [bio, setBio] = useState(user?.bio || '');
  const [avatar, setAvatar] = useState<string | null>(user?.avatar || null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pickAvatar = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission needed', 'We need access to your photos to set an avatar.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.55,
      base64: true,
      allowsEditing: true,
      aspect: [1, 1],
    });
    if (!result.canceled && result.assets[0]?.base64) {
      setAvatar(`data:image/jpeg;base64,${result.assets[0].base64}`);
      Haptics.selectionAsync().catch(() => {});
    }
  };

  const save = async () => {
    setErr(null);
    if (!displayName.trim()) {
      setErr('Display name is required');
      return;
    }
    setSaving(true);
    try {
      const payload: any = {
        display_name: displayName.trim(),
        home_course: homeCourse.trim(),
        bio: bio.trim(),
        avatar,
      };
      const hc = handicap.trim();
      if (hc.length > 0) {
        const n = Number(hc);
        if (!Number.isFinite(n)) {
          setErr('Handicap must be a number');
          setSaving(false);
          return;
        }
        payload.handicap = n;
      } else {
        payload.handicap = null;
      }
      const updated = await api.updateMe(payload);
      setUser(updated);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.back();
    } catch (e: any) {
      setErr(e?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const initials = (displayName || 'G')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <View style={styles.container} testID="profile-edit-screen">
      <SafeAreaView edges={['top']} style={styles.topBar}>
        <Pressable testID="profile-edit-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Edit profile</Text>
        <View style={{ width: 44 }} />
      </SafeAreaView>

      <KeyboardAwareScrollView
        contentContainerStyle={styles.form}
        keyboardShouldPersistTaps="handled"
        bottomOffset={20}
      >
          <View style={styles.avatarWrap}>
            <View style={styles.avatarLarge}>
              {avatar ? (
                <Image source={{ uri: avatar }} style={{ width: '100%', height: '100%' }} />
              ) : (
                <Text style={styles.avatarInitials}>{initials}</Text>
              )}
            </View>
            <Pressable testID="profile-edit-pick-avatar" onPress={pickAvatar} style={styles.avatarBtn}>
              <Ionicons name="camera" size={15} color={colors.onBrandPrimary} />
              <Text style={styles.avatarBtnText}>{avatar ? 'Change photo' : 'Add photo'}</Text>
            </Pressable>
            {avatar ? (
              <Pressable testID="profile-edit-remove-avatar" onPress={() => setAvatar(null)} hitSlop={8}>
                <Text style={styles.avatarRemove}>Remove</Text>
              </Pressable>
            ) : null}
          </View>

          <TBInput
            label="Display name"
            testID="profile-edit-name"
            value={displayName}
            onChangeText={setDisplayName}
            placeholder="Your name"
          />
          <TBInput
            label="Handicap index"
            testID="profile-edit-handicap"
            value={handicap}
            onChangeText={setHandicap}
            keyboardType="decimal-pad"
            placeholder="e.g. 12.4"
          />
          <TBInput
            label="Home course"
            testID="profile-edit-home"
            value={homeCourse}
            onChangeText={setHomeCourse}
            placeholder="Pebble Meadows GC"
          />
          <TBInput
            label="Bio"
            testID="profile-edit-bio"
            value={bio}
            onChangeText={setBio}
            multiline
            placeholder="Weekend warrior. Fairways or nothing."
            style={{ minHeight: 90, textAlignVertical: 'top' }}
          />
          {err ? <Text style={styles.errText}>{err}</Text> : null}
          <TBButton
            label={saving ? 'Saving…' : 'Save changes'}
            testID="profile-edit-save"
            loading={saving}
            onPress={save}
            style={{ marginTop: spacing.md }}
          />
      </KeyboardAwareScrollView>
        {saving ? (
          <View style={styles.overlay} pointerEvents="none">
            <ActivityIndicator color={colors.brandPrimary} size="large" />
          </View>
        ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
    justifyContent: 'space-between',
  },
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  title: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  form: { padding: spacing.xl, gap: spacing.md, paddingBottom: spacing.xxxl },
  avatarWrap: { alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
  avatarLarge: {
    width: 110,
    height: 110,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    ...shadow.card,
  },
  avatarInitials: { fontSize: 36, fontWeight: '800', color: colors.onBrandTertiary },
  avatarBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    ...shadow.soft,
  },
  avatarBtnText: { color: colors.onBrandPrimary, fontWeight: '800', fontSize: 13 },
  avatarRemove: { color: colors.error, fontSize: 12, fontWeight: '700' },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(253,252,248,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
