import React from 'react';

/**
 * AdMob (react-native-google-mobile-ads) has been removed.
 *
 * The native module is incompatible with React Native 0.81 / the New
 * Architecture — its Kotlin source references `currentActivity` /
 * `runOnUiThread`, which fail to compile and broke the production
 * (`compileReleaseKotlin`) build. It also crashed the app inside Expo Go where
 * the native binary does not exist.
 *
 * These are cross-platform no-op stubs so the existing imports in
 * `app/_layout.tsx` and `app/(tabs)/index.tsx` keep working on web and native
 * without pulling in any native module. Ads can be re-introduced later with a
 * New-Architecture-compatible SDK version.
 */
export function FeedNativeAd(): React.ReactElement | null {
  return null;
}

export async function initAdMob(): Promise<void> {
  // No-op: ads are disabled.
}
