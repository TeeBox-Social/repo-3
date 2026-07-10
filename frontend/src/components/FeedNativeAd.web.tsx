/**
 * Web stub for FeedNativeAd. AdMob has no web SDK, and importing
 * `react-native-google-mobile-ads` on web trips Metro because it references
 * native-only React Native internals. Metro auto-picks the `.web.tsx` file
 * when building for the web platform, so this file keeps the web bundle
 * clean while the `.native.tsx` sibling handles Android/iOS.
 */
import React from 'react';

export function FeedNativeAd() {
  return null;
}

export async function initAdMob(): Promise<void> {
  // No-op on web.
}
