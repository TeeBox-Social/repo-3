import React, { useCallback } from 'react';
import { Text, TextStyle, StyleProp } from 'react-native';
import { useRouter } from 'expo-router';
import { colors } from '@/src/theme';
import { api } from '@/src/api';

type Props = {
  text: string;
  style?: StyleProp<TextStyle>;
  mentionStyle?: StyleProp<TextStyle>;
  numberOfLines?: number;
};

/**
 * Renders text with `@Display_Name` tokens turned into tappable chips that
 * navigate to the mentioned user's profile.
 *
 * How tokens are matched: `@` followed by one or more word chars. Because the
 * MentionInput swaps spaces for underscores when inserting, we translate the
 * underscores back before hitting the resolve endpoint.
 *
 * If the mentioned name can't be resolved (user deleted / typo), the tap is a
 * silent no-op — we don't want a scary error toast for a stale tag.
 */
export function MentionText({ text, style, mentionStyle, numberOfLines }: Props) {
  const router = useRouter();
  const parts = String(text || '').split(/(@[A-Za-z0-9_]+)/g);

  const onTapMention = useCallback(
    async (token: string) => {
      // Strip leading '@' and swap underscores → spaces for the lookup.
      const name = token.slice(1);
      try {
        const res = await api.getUserByName(name);
        if (res?.id) {
          router.push(`/user/${res.id}`);
        }
      } catch {
        // Silent — tag was probably outdated
      }
    },
    [router],
  );

  return (
    <Text style={style} numberOfLines={numberOfLines}>
      {parts.map((p, i) =>
        p.startsWith('@') ? (
          <Text
            key={i}
            style={[{ color: colors.brandPrimary, fontWeight: '700' as const }, mentionStyle]}
            onPress={() => onTapMention(p)}
            suppressHighlighting
          >
            {p}
          </Text>
        ) : (
          <Text key={i}>{p}</Text>
        ),
      )}
    </Text>
  );
}
