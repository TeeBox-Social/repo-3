import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  Pressable,
  TextInputProps,
  ActivityIndicator,
  Platform,
  ScrollView,
} from 'react-native';
import { Image } from 'expo-image';
import { colors, radius, spacing } from '@/src/theme';
import { api } from '@/src/api';

type Suggestion = { id: string; display_name: string; avatar?: string | null };

type Props = TextInputProps & {
  value: string;
  onChangeText: (text: string) => void;
  onMentionsChange?: (ids: string[]) => void;
  /**
   * Where the suggestions dropdown should render relative to the input.
   * - `top` (default): above the input — best when the input sits near the
   *   bottom of the screen (e.g. the comment bar on a post detail).
   * - `bottom`: below the input — best when the input sits high in the layout
   *   with lots of empty space beneath it (e.g. the Notes/Details field on
   *   the Log screen for Post / LFG modes).
   */
  dropdownPlacement?: 'top' | 'bottom';
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
  dropdownPlacement = 'top',
  ...rest
}: Props) {
  const inputRef = useRef<TextInput | null>(null);
  const [caret, setCaret] = useState(0);
  const [selection, setSelection] = useState<{ start: number; end: number } | undefined>(undefined);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [queried, setQueried] = useState(false);
  const [mentionIds, setMentionIds] = useState<string[]>([]);

  // Memoize the active-mention detection so its identity is stable across
  // unrelated re-renders (parent state changes, keyboard-avoiding view resize,
  // etc). Without this the search useEffect below would re-fire every render
  // and cause the suggestions dropdown to visibly flicker.
  const active = useMemo(() => activeMention(value, caret), [value, caret]);
  const token = active?.token ?? null;

  useEffect(() => {
    if (token === null) {
      // Only clear if we actually have something to clear; avoids a needless
      // state churn on every render when the user is not composing a mention.
      setSuggestions((prev) => (prev.length === 0 ? prev : []));
      setLoading(false);
      setQueried(false);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(async () => {
      if (cancelled) return;
      setLoading(true);
      try {
        const users = await api.discoverUsers(token, true);
        // Now that the dropdown is scrollable, show a healthier set of matches
        // (12 is enough to cover most typical friend lists without punishing
        // rendering perf on lower-end devices).
        if (!cancelled) {
          setSuggestions(users.slice(0, 12));
          setQueried(true);
        }
      } catch {
        // Preserve previous suggestions on transient errors — flickering to an
        // empty list and back is more jarring than showing stale results for a
        // moment.
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [token]);


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

  const isOpen = !!(suggestions.length > 0 || (active && (loading || queried)));

  const suggestionsPanel = isOpen ? (
    <View
      testID="mention-suggestions"
      style={[
        styles.suggestBox,
        dropdownPlacement === 'bottom' ? styles.suggestBoxBottom : styles.suggestBoxTop,
      ]}
    >
      {loading ? (
        <View style={styles.suggestLoading}>
          <ActivityIndicator size="small" color={colors.brandPrimary} />
        </View>
      ) : suggestions.length === 0 ? (
        <View style={styles.suggestEmpty} testID="mention-suggestions-empty">
          <Text style={styles.suggestEmptyTitle}>No matching connections</Text>
          <Text style={styles.suggestEmptySub}>
            You can only tag golfers you follow or who follow you.
          </Text>
        </View>
      ) : (
        <ScrollView
          testID="mention-suggestions-scroll"
          style={styles.suggestScroll}
          keyboardShouldPersistTaps="always"
          nestedScrollEnabled
          showsVerticalScrollIndicator
        >
          {suggestions.map((s) => {
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
          })}
        </ScrollView>
      )}
    </View>
  ) : null;

  return (
    <View
      style={[
        styles.wrapper,
        isOpen && styles.wrapperOpen,
      ]}
    >
      {dropdownPlacement === 'top' ? suggestionsPanel : null}

      <TextInput
        ref={inputRef}
        {...rest}
        value={value}
        onChangeText={(next) => {
          // On Android in particular, `onSelectionChange` fires ~1 frame
          // AFTER `onChangeText`, so between those two events the caret state
          // is stale and `activeMention(value, caret)` briefly returns the
          // wrong (or a null) token — causing the suggestions dropdown to
          // flicker. When the user is simply appending text (the most common
          // case for typing "@name"), we can safely snap the caret to the end
          // of the new value immediately. For mid-string edits, we leave the
          // caret alone and let `onSelectionChange` correct it.
          if (next.length >= value.length && next.startsWith(value)) {
            setCaret(next.length);
          }
          onChangeText(next);
        }}
        onSelectionChange={(e) => setCaret(e.nativeEvent.selection.start)}
        selection={selection}
        style={style}
        placeholderTextColor={colors.muted}
      />

      {dropdownPlacement === 'bottom' ? suggestionsPanel : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    width: '100%',
    position: 'relative',
    // Give the wrapper a small base z-index so its absolute-positioned child
    // (the dropdown) always paints above the input itself.
    zIndex: 1,
  },
  wrapperOpen: {
    // When the picker is open, lift the entire component well above later
    // siblings on both web (zIndex) and native (elevation).
    zIndex: 1000,
    elevation: 20,
  },
  suggestBox: {
    // Solid, opaque panel — used for both inline (bottom placement) and
    // floating (top placement) variants. Placement styles below add / remove
    // absolute positioning as needed.
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    overflow: 'hidden',
    zIndex: 1000,
    elevation: 20,
    shadowColor: '#000',
    shadowOpacity: 0.22,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
  },
  suggestBoxTop: {
    // Floats above the input — used when the input sits near the bottom of
    // the screen (e.g. the post-detail comment bar), so we can't push content
    // below it.
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: '100%',
    marginBottom: spacing.xs,
  },
  suggestBoxBottom: {
    // Renders inline as a normal sibling — pushes the following form content
    // (Photos, submit button, tip) further down while the picker is open, so
    // nothing can visually overlap the tag list. When the picker closes,
    // content springs back into place.
    marginTop: spacing.xs,
    marginBottom: spacing.xs,
  },
  suggestScroll: {
    // Cap the dropdown so a long friends list doesn't push offscreen.
    // ~5 rows visible at once (each row is ~54px including padding),
    // remaining rows are reachable via scroll.
    maxHeight: 264,
  },
  suggestRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    // Solid backdrop on each row too — belt & braces so nothing shows through
    // if a parent layer ever becomes translucent.
    backgroundColor: colors.surfaceSecondary,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  suggestName: { fontSize: 14, fontWeight: '700', color: colors.onSurface },
  suggestLoading: {
    paddingVertical: 14,
    alignItems: 'center',
    backgroundColor: colors.surfaceSecondary,
  },
  suggestEmpty: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    gap: 4,
    backgroundColor: colors.surfaceSecondary,
  },
  suggestEmptyTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: colors.onSurface,
  },
  suggestEmptySub: {
    fontSize: 12,
    color: colors.muted,
    lineHeight: 16,
  },
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
