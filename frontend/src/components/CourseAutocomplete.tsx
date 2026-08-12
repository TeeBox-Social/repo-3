import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  TextInput,
  ActivityIndicator,
  Modal,
} from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';

type CourseHit = {
  id: string;
  name: string;
  city?: string | null;
  region?: string | null;
  country?: string | null;
  par?: number | null;
  verified: boolean;
  submitted_by_me: boolean;
};

type Props = {
  value: string;
  selected: boolean;
  onSelect: (course: { name: string; par?: number | null }) => void;
  onChangeText: (text: string) => void;
  placeholder?: string;
  testID?: string;
};

/**
 * Autocomplete over the course library. Users must pick from suggestions;
 * if nothing matches they can tap "Add [xyz] as new course" which opens a
 * mini-form asking for full course name and par-18. Newly submitted courses
 * are stored with verified=false and used immediately for the round; an
 * admin must approve them before they surface in Discover.
 *
 * `selected` is a controlled prop from the parent so it stays in sync with
 * the parent's picked/unpicked state without racing against onChangeText.
 */
export function CourseAutocomplete({ value, selected, onSelect, onChangeText, placeholder, testID }: Props) {
  useTheme();
  const [query, setQuery] = useState(value);
  const [suggestions, setSuggestions] = useState<CourseHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const doSearch = useCallback(async (q: string) => {
    if (!q || q.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    setLoading(true);
    try {
      const hits = await api.searchCourses(q.trim());
      setSuggestions(hits);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChangeText = (text: string) => {
    setQuery(text);
    onChangeText(text);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(text), 220);
  };

  const pickCourse = (c: CourseHit) => {
    setQuery(c.name);
    setFocused(false);
    setSuggestions([]);
    onSelect({ name: c.name, par: c.par ?? null });
  };

  const openAddModal = () => {
    setFocused(false);
    setShowAddModal(true);
  };

  const showSuggestions =
    focused && !selected && (query.trim().length >= 2);

  return (
    <View style={styles.wrap} testID={testID}>
      <Text style={styles.label}>Course</Text>
      <View style={[styles.inputWrap, focused && styles.inputWrapFocus, selected && styles.inputWrapLocked]}>
        {selected ? (
          <Ionicons name="checkmark-circle" size={18} color={colors.brandPrimary} />
        ) : (
          <Ionicons name="search" size={18} color={colors.muted} />
        )}
        <TextInput
          value={query}
          onChangeText={handleChangeText}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 200)}
          placeholder={placeholder || 'Start typing to find your course…'}
          placeholderTextColor={colors.muted}
          style={styles.input}
          testID={`${testID}-input`}
          autoCorrect={false}
          autoCapitalize="words"
        />
        {query.length > 0 ? (
          <Pressable
            hitSlop={8}
            onPress={() => {
              setQuery('');
              setSuggestions([]);
              onChangeText('');
              onSelect({ name: '' });
            }}
            testID={`${testID}-clear`}
          >
            <Ionicons name="close-circle" size={18} color={colors.muted} />
          </Pressable>
        ) : null}
      </View>

      {selected ? (
        <View style={styles.pickedRow}>
          <Ionicons name="flag" size={12} color={colors.brandPrimary} />
          <Text style={styles.pickedText}>Course selected</Text>
        </View>
      ) : null}

      {showSuggestions ? (
        <View style={styles.dropdown} testID={`${testID}-dropdown`}>
          {loading ? (
            <View style={styles.dropdownLoading}>
              <ActivityIndicator size="small" color={colors.brandPrimary} />
              <Text style={styles.dropdownLoadingText}>Searching…</Text>
            </View>
          ) : suggestions.length > 0 ? (
            suggestions.slice(0, 8).map((c) => (
              <Pressable
                key={c.id}
                onPress={() => pickCourse(c)}
                style={({ pressed }) => [styles.suggestion, pressed && { backgroundColor: colors.surfaceSecondary }]}
                testID={`${testID}-hit-${c.id}`}
              >
                <View style={styles.suggestionIcon}>
                  <Ionicons name="golf" size={16} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.suggestionTitle} numberOfLines={1}>
                    {c.name}
                    {!c.verified ? <Text style={styles.pendingTag}>  · Pending</Text> : null}
                  </Text>
                  {c.city || c.region || c.country ? (
                    <Text style={styles.suggestionSub} numberOfLines={1}>
                      {[c.city, c.region, c.country].filter(Boolean).join(', ')}
                    </Text>
                  ) : null}
                </View>
              </Pressable>
            ))
          ) : (
            <View style={styles.dropdownEmpty}>
              <Text style={styles.dropdownEmptyText}>No matches for &quot;{query.trim()}&quot;</Text>
            </View>
          )}

          {/* Always show Add-this-course action when the user has typed something */}
          {query.trim().length >= 3 && !loading ? (
            <Pressable
              onPress={openAddModal}
              style={({ pressed }) => [styles.addRow, pressed && { opacity: 0.7 }]}
              testID={`${testID}-add-new`}
            >
              <View style={[styles.suggestionIcon, { backgroundColor: colors.brandPrimary }]}>
                <Ionicons name="add" size={16} color="#fff" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.addTitle}>Add &quot;{query.trim()}&quot; as a new course</Text>
                <Text style={styles.addSub}>Waiting on admin verification — you can still post your round.</Text>
              </View>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      <AddCourseModal
        visible={showAddModal}
        initialName={query}
        onClose={() => setShowAddModal(false)}
        onCreated={(c) => {
          setShowAddModal(false);
          pickCourse({
            id: c.id,
            name: c.name,
            par: c.par,
            city: c.city,
            region: c.region,
            country: c.country,
            verified: !!c.verified,
            submitted_by_me: true,
          });
        }}
      />
    </View>
  );
}

function AddCourseModal({
  visible,
  initialName,
  onClose,
  onCreated,
}: {
  visible: boolean;
  initialName: string;
  onClose: () => void;
  onCreated: (course: any) => void;
}) {
  const [name, setName] = useState(initialName);
  const [par, setPar] = useState('72');
  const [city, setCity] = useState('');
  const [region, setRegion] = useState('');
  const [country, setCountry] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      setName(initialName);
      setPar('72');
      setCity('');
      setRegion('');
      setCountry('');
      setError(null);
    }
  }, [visible, initialName]);

  const handleSave = async () => {
    setError(null);
    const trimmed = name.trim();
    if (trimmed.length < 3) {
      setError('Full course name is required (at least 3 characters).');
      return;
    }
    const parNum = Number(par);
    if (!Number.isFinite(parNum) || parNum < 27 || parNum > 90) {
      setError('Enter a par between 27 and 90 for 18 holes.');
      return;
    }
    setSaving(true);
    try {
      const res = await api.submitCourse({
        name: trimmed,
        par: parNum,
        city: city.trim() || undefined,
        region: region.trim() || undefined,
        country: country.trim() || undefined,
      });
      onCreated(res.course);
    } catch (e: any) {
      setError(e?.message || 'Could not save the course. Try a different name.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior="padding"
        keyboardVerticalOffset={20}
        style={styles.modalRoot}
      >
        <Pressable style={styles.modalBackdrop} onPress={onClose} />
        <View style={styles.modalCard} testID="add-course-modal">
          <View style={styles.modalGrabber} />
          <Text style={styles.modalTitle}>Add a new course</Text>
          <Text style={styles.modalSub}>
            Help build TeeBox. An admin reviews new courses — your round posts immediately.
          </Text>

          <TBInput
            label="Full course name"
            value={name}
            onChangeText={setName}
            placeholder="e.g. Pebble Meadows GC"
            testID="add-course-name"
            autoCapitalize="words"
          />
          <TBInput
            label="Par for 18 holes"
            value={par}
            onChangeText={setPar}
            keyboardType="number-pad"
            placeholder="72"
            testID="add-course-par"
          />
          <View style={styles.addRow2}>
            <TBInput
              label="City (optional)"
              value={city}
              onChangeText={setCity}
              testID="add-course-city"
              containerStyle={{ flex: 1 }}
            />
            <TBInput
              label="Region (optional)"
              value={region}
              onChangeText={setRegion}
              testID="add-course-region"
              containerStyle={{ flex: 1 }}
            />
          </View>
          <TBInput
            label="Country (optional)"
            value={country}
            onChangeText={setCountry}
            testID="add-course-country"
          />

          {error ? <Text style={styles.modalError}>{error}</Text> : null}

          <View style={styles.modalActions}>
            <Pressable onPress={onClose} style={styles.modalCancel} disabled={saving}>
              <Text style={styles.modalCancelText}>Cancel</Text>
            </Pressable>
            <TBButton
              label={saving ? 'Saving…' : 'Submit for review'}
              loading={saving}
              onPress={handleSave}
              testID="add-course-submit"
              style={{ flex: 1 }}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  wrap: { gap: 6 },
  label: { fontSize: 13, fontWeight: '700', color: colors.onSurface, letterSpacing: 0.2 },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    height: 46,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  inputWrapFocus: { borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  inputWrapLocked: { borderColor: colors.brandPrimary, backgroundColor: '#F0FBF3' },
  input: { flex: 1, fontSize: 15, color: colors.onSurface, paddingVertical: 0 },
  pickedRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  pickedText: { fontSize: 11, color: colors.brandPrimary, fontWeight: '700' },
  dropdown: {
    marginTop: 4,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.soft,
    overflow: 'hidden',
  },
  dropdownLoading: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: spacing.md },
  dropdownLoadingText: { fontSize: 13, color: colors.muted },
  dropdownEmpty: { padding: spacing.md },
  dropdownEmptyText: { fontSize: 13, color: colors.muted },
  suggestion: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  suggestionIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  suggestionTitle: { fontSize: 14, fontWeight: '700', color: colors.onSurface },
  suggestionSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  pendingTag: { fontSize: 11, color: colors.muted, fontWeight: '600' },
  addRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    backgroundColor: colors.brandTertiary,
  },
  addTitle: { fontSize: 14, fontWeight: '800', color: colors.onBrandTertiary },
  addSub: { fontSize: 12, color: colors.onBrandTertiary, opacity: 0.85, marginTop: 2 },
  // Modal
  modalRoot: { flex: 1, justifyContent: 'flex-end' },
  modalBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(19,42,28,0.55)' },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: spacing.xl,
    gap: spacing.md,
    ...shadow.card,
  },
  modalGrabber: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.md,
  },
  modalTitle: { fontSize: 20, fontWeight: '800', color: colors.onSurface },
  modalSub: { fontSize: 13, color: colors.muted, lineHeight: 18 },
  addRow2: { flexDirection: 'row', gap: spacing.sm },
  modalError: { color: colors.error, fontSize: 13, fontWeight: '700' },
  modalActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.sm },
  modalCancel: { paddingHorizontal: spacing.md, paddingVertical: 12 },
  modalCancelText: { fontSize: 15, fontWeight: '700', color: colors.muted },
}));
