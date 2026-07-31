/**
 * AdMob Native Advanced ad card styled to blend with the RoundCard visual
 * language. Rendered inline in the Feed FlatList by `<Feed />` every N posts.
 *
 * Test IDs are used on iOS at all times (per user's iOS setup); Android uses
 * the real Ad Unit ID in production and the Google test ID during __DEV__
 * so we never accidentally self-click a real ad.
 *
 * The component is a safe no-op on web (AdMob has no web support) and while
 * the ad is still loading, so the FlatList height stays stable.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Image, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import Constants, { ExecutionEnvironment } from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing } from '@/src/theme';

// AdMob's native module (RNGoogleMobileAdsModule) is NOT bundled into Expo Go —
// requiring `react-native-google-mobile-ads` there throws a hard
// `TurboModuleRegistry.getEnforcing(...) could not be found` error that crashes
// the app. Only dev-client / standalone / production builds contain the native
// binary, so we gate ALL access to the module behind this flag.
const isExpoGo = Constants.executionEnvironment === ExecutionEnvironment.StoreClient;

// Google's public test Ad Unit IDs — safe to click during development.
const TEST_NATIVE_AD_UNIT = {
  android: 'ca-app-pub-3940256099942544/2247696110',
  ios: 'ca-app-pub-3940256099942544/3986624511',
};

// Real production ad unit IDs. Only Android is real for now; iOS keeps test.
const PROD_NATIVE_AD_UNIT = {
  android: 'ca-app-pub-1035050955026373/1152948499',
  ios: TEST_NATIVE_AD_UNIT.ios, // no production iOS unit yet — safe test
};

function pickAdUnitId(): string {
  const platform = Platform.OS === 'ios' ? 'ios' : 'android';
  if (__DEV__) return TEST_NATIVE_AD_UNIT[platform];
  return PROD_NATIVE_AD_UNIT[platform];
}

// Dynamic import so the web bundle (and Expo Go) never tries to load the
// native module — it throws immediately on import in unsupported runtimes.
// NOTE: we deliberately avoid `typeof import('react-native-google-mobile-ads')`
// as the type alias — Metro treats it as a real import and blows up the web
// bundle with "Importing native-only module ... on web".
let adsModulePromise: Promise<any | null> | null = null;
function loadAdsModule(): Promise<any | null> {
  // Web has no AdMob; Expo Go has no native binary for it. Bail before the
  // require() so we never hit the TurboModule "could not be found" crash.
  if (Platform.OS === 'web' || isExpoGo) return Promise.resolve(null);
  if (!adsModulePromise) {
    adsModulePromise = (async () => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const mod = require('react-native-google-mobile-ads');
        return mod;
      } catch {
        // Expo Go / preview: the native module isn't present.
        return null;
      }
    })();
  }
  return adsModulePromise;
}

/** Initialize the AdMob SDK once per app session. Safe on web (no-op). */
export async function initAdMob(): Promise<void> {
  const mod = await loadAdsModule();
  if (!mod) return;
  try {
    await mod.default().initialize();
  } catch {
    // Best-effort — never throw during init.
  }
}
export function FeedNativeAd() {
  const [nativeAd, setNativeAd] = useState<any | null>(null);
  const [failed, setFailed] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    (async () => {
      const mod = await loadAdsModule();
      if (!mod || !mounted.current) return;
      try {
        const { NativeAd, NativeMediaAspectRatio } = mod;
        const ad = await NativeAd.createForAdRequest(pickAdUnitId(), {
          requestNonPersonalizedAdsOnly: true,
          aspectRatio: NativeMediaAspectRatio?.LANDSCAPE,
        });
        if (mounted.current) setNativeAd(ad);
      } catch {
        if (mounted.current) setFailed(true);
      }
    })();
    return () => {
      mounted.current = false;
      // Some versions expose a destroy() to free the underlying view.
      try {
        (nativeAd as any)?.destroy?.();
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Web / Expo Go / load failure / still loading → render nothing to keep the
  // FlatList height stable and avoid layout jumps.
  if (Platform.OS === 'web' || failed || !nativeAd) return null;

  return <RenderedNativeAd nativeAd={nativeAd} />;
}

/** Broken out so we can require() the NativeAdView/NativeAsset primitives lazily. */
function RenderedNativeAd({ nativeAd }: { nativeAd: any }) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const mod = require('react-native-google-mobile-ads');
  const { NativeAdView, NativeAsset, NativeAssetType } = mod;

  const icon = nativeAd.icon?.url;
  const heroImg = nativeAd.images?.[0]?.url;

  return (
    <NativeAdView nativeAd={nativeAd} style={styles.card}>
      {/* Sponsored header row */}
      <View style={styles.header}>
        {icon ? (
          <NativeAsset assetType={NativeAssetType.ICON}>
            <Image source={{ uri: icon }} style={styles.icon} />
          </NativeAsset>
        ) : (
          <View style={styles.iconFallback}>
            <Ionicons name="megaphone-outline" size={18} color={colors.brandPrimary} />
          </View>
        )}
        <View style={{ flex: 1 }}>
          <NativeAsset assetType={NativeAssetType.HEADLINE}>
            <Text style={styles.headline} numberOfLines={1}>
              {nativeAd.headline}
            </Text>
          </NativeAsset>
          <View style={styles.sponsoredRow}>
            <View style={styles.sponsoredPill}>
              <Text style={styles.sponsoredText}>Sponsored</Text>
            </View>
            {nativeAd.advertiser ? (
              <Text style={styles.advertiser} numberOfLines={1}>
                {nativeAd.advertiser}
              </Text>
            ) : null}
          </View>
        </View>
      </View>

      {/* Hero image */}
      {heroImg ? (
        <NativeAsset assetType={NativeAssetType.IMAGE}>
          <Image source={{ uri: heroImg }} style={styles.hero} resizeMode="cover" />
        </NativeAsset>
      ) : null}

      {/* Body */}
      {nativeAd.body ? (
        <NativeAsset assetType={NativeAssetType.BODY}>
          <Text style={styles.body} numberOfLines={3}>
            {nativeAd.body}
          </Text>
        </NativeAsset>
      ) : null}

      {/* CTA */}
      {nativeAd.callToAction ? (
        <NativeAsset assetType={NativeAssetType.CALL_TO_ACTION}>
          <Pressable style={styles.cta} testID="feed-native-ad-cta">
            <Text style={styles.ctaText}>{nativeAd.callToAction}</Text>
            <Ionicons name="arrow-forward" size={14} color="#fff" />
          </Pressable>
        </NativeAsset>
      ) : null}
    </NativeAdView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    ...shadow.card,
    gap: spacing.md,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  icon: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.brandTertiary },
  iconFallback: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headline: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  sponsoredRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  sponsoredPill: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: '#FFF4D6',
    borderWidth: 1,
    borderColor: '#F0DBA0',
  },
  sponsoredText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#7A4E00',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  advertiser: { fontSize: 12, color: colors.muted, fontWeight: '600', flex: 1 },
  hero: {
    width: '100%',
    height: 180,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
  },
  body: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
  cta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    alignSelf: 'flex-start',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  ctaText: { color: '#fff', fontWeight: '800', fontSize: 13 },
});
