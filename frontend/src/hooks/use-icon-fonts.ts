// Icon font loader for Expo apps. Fonts are loaded from a CDN only under
// Expo Go (StoreClient) — that's where @expo/vector-icons' .ttf files come
// back as 0 bytes from Metro's asset resolver on Android. Native dev/prod
// builds and web pass an empty map, so useFonts resolves to [true, null]
// immediately via react-native-vector-icons autolinking / web stubs.
// ICON_VECTOR_VERSION must match @expo/vector-icons in package.json.
// Usage: const [loaded, error] = useIconFonts();

import { Platform } from "react-native";
import Constants, { ExecutionEnvironment } from "expo-constants";
import { useFonts } from "expo-font";
import Ionicons from "@expo/vector-icons/Ionicons";

// Ionicons is the ONLY @expo/vector-icons family the app renders, so we only
// need to preload that one font. WHERE we load it from depends on the runtime:
//
//  • Expo Go (StoreClient): the bundled .ttf is served to the device as an
//    EMPTY (0-byte) file over the Metro dev tunnel — useFonts(Ionicons.font)
//    then rejects with "Font file for ionicons is empty". So we fetch the real
//    font bytes from the jsDelivr CDN instead. (Version must match the
//    installed @expo/vector-icons so the glyph map lines up.)
//  • Dev-client / standalone / production builds: the .ttf is bundled straight
//    into the native binary and resolves correctly, so we use the reliable,
//    offline-friendly local map.
//  • Web: @expo/vector-icons injects its own @font-face, so an empty map is
//    enough and resolves to [true, null] on the first render.
//
// Combined with the render-gating in app/_layout.tsx (the tree only mounts
// after this resolves), the 'ionicons' family is registered BEFORE any
// <Ionicons> mounts — so @expo/vector-icons never auto-loads the empty local
// copy that used to blank the screen.
const ICON_VECTOR_VERSION = "15.1.1";
const IONICONS_CDN = `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/Ionicons.ttf`;

function iconFontMap(): Record<string, any> {
  if (Platform.OS === "web") return {};
  if (Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
    return { ionicons: IONICONS_CDN };
  }
  return Ionicons.font;
}

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts(iconFontMap());
