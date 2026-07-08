import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  Pressable,
  TextInputProps,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { Image } from 'expo-image';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';

type Suggestion = { id: string; display_name: string; avatar?: string | null };

type Props = TextInputProps & {
  value: string;
  onChangeText: (text: string) => void;
  onMentionsChange?: (ids: string[]) => void;
};

/** Detects the currently-typed @mention token at cursor position. */
function activeMention(text: string, caret: number): { start: number; token: string } | null {
  if (caret <= 0) return null;
  const before = text.slice(0, caret);
  const atIdx = before.lastIndexOf('@');
  if (atIdx < 0) return null;
  const boundaryOk = atIdx === 0 || /\s/.test(before[atIdx - 1]);
  if (!boundaryOk) return null;
  const token = before.slice(atIdx + 1);
  if (/\s/.test(token)) return null;
  return { start: atIdx, token };
}

export function MentionInput({
  value,
  onChangeText,
  onMentionsChange,
  style,
  ...rest
}: Props) {
  const inputRef = useRef<TextInput | null>(null);
  const [caret, setCaret] = useState(0);
  const [selection, setSelection] = useState<{ start: number; end: number } | undefined>(undefined);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [mentionIds, setMentionIds] = useState<string[]>([]);
  const active = activeMention(value, caret);

  const search = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const users = await api.discoverUsers(q);
      setSuggestions(users.slice(0, 6));
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!active) {
      setSuggestions([]);
      return;
    }
    const t = setTimeout(() => search(active.token), 180);
    return () => clearTimeout(t);
  }, [active?.token, search, active]);

  const pick = (u: Suggestion) => {
    if (!active) return;
    const insert = u.display_name.replace(/\s+/g, '_');
    const before = value.slice(0, active.start);
    const after = value.slice(caret);
    const next = `${before}@${insert} ${after}`;
    onChangeText(next);
    setSuggestions([]);
    const newIds = mentionIds.includes(u.id) ? mentionIds : [...mentionIds, u.id];
    setMentionIds(newIds);
    onMentionsChange?.(newIds);
    // Move caret past inserted mention + space (declarative for web, imperative on native)
    const nextCaret = before.length + 1 + insert.length + 1;
    setCaret(nextCaret);
    if (Platform.OS === 'web') {
      setSelection({ start: nextCaret, end: nextCaret });
      // Clear so we don't fight user typing on subsequent renders
      setTimeout(() => setSelection(undefined), 0);
    } else {
      setTimeout(() => {
        try {
          inputRef.current?.setNativeProps?.({ selection: { start: nextCaret, end: nextCaret } });
        } catch {}
      }, 0);
    }
  };

  return (
    <View style={{ width: '100%', position: 'relative' }}>
      {suggestions.length > 0 || (active && loading) ? (
        <View style={styles.suggestBox} testID="mention-suggestions" pointerEvents="box-none">
          {loading ? (
            <View style={styles.suggestLoading}>
              <ActivityIndicator size="small" color={colors.brandPrimary} />
            </View>
          ) : (
            suggestions.map((s) => {
              const initials = s.display_name
                .split(' ')
                .map((p) => p[0])
                .slice(0, 2)
                .join('')
                .toUpperCase();
              return (
                <Pressable
                  key={s.id}
                  testID={`mention-suggest-${s.id}`}
                  onPress={() => pick(s)}
                  style={styles.suggestRow}
                >
                  <View style={styles.avatar}>
                    {s.avatar ? (
                      <Image source={{ uri: s.avatar }} style={{ width: '100%', height: '100%' }} />
                    ) : (
                      <Text style={styles.avatarText}>{initials}</Text>
                    )}
                  </View>
                  <Text style={styles.suggestName}>@{s.display_name}</Text>
                </Pressable>
              );
            })
          )}
        </View>
      ) : null}

      <TextInput
        ref={inputRef}
        {...rest}
        value={value}
        onChangeText={onChangeText}
        onSelectionChange={(e) => setCaret(e.nativeEvent.selection.start)}
        selection={selection}
        style={style}
        placeholderTextColor={colors.muted}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  suggestBox: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: '100%',
    marginBottom: spacing.xs,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
    zIndex: 999,
    elevation: 12,
    ...shadow.soft,
  },
  suggestRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  suggestName: { fontSize: 14, fontWeight: '700', color: colors.onSurface },
  suggestLoading: { paddingVertical: 14, alignItems: 'center' },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 11 },
});
